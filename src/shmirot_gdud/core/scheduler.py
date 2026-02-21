from typing import List, Dict, Optional, Tuple, Callable, Set, Any
from .models import Group, Schedule, ScheduleSlot
from .config import config
from .base.context import ScheduleContext
from shmirot_gdud.core.constraints.implementations import StaffingRuleConstraint
import random
import math
import time
from datetime import datetime, timedelta

DISABLED_ID = "DISABLED"

class ScheduleState:
    def __init__(self, schedule: Schedule, groups: List[Group], hard_start: int, hard_end: int):
        self.schedule = schedule
        self.groups = {g.id: g for g in groups}
        self.hard_start = hard_start
        self.hard_end = hard_end
        
        self.slot_map: Dict[Tuple[str, int, int], ScheduleSlot] = {}
        for s in schedule.slots:
            self.slot_map[(s.date, s.hour, s.position)] = s
            
        start_date = datetime.strptime(schedule.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(schedule.end_date, "%Y-%m-%d")
        self.time_points = []
        curr = start_date
        while curr <= end_date:
            d_str = curr.strftime("%Y-%m-%d")
            for h in range(24):
                self.time_points.append((d_str, h))
            curr += timedelta(days=1)
            
        self.time_to_index = {t: i for i, t in enumerate(self.time_points)}
        
        self.group_hard_hours = {g_id: 0 for g_id in self.groups}
        self.group_daily_counts = {} 
        
        for s in schedule.slots:
            if not s.group_id or s.group_id == DISABLED_ID: continue
            self._add_to_state(s)

    def _add_to_state(self, slot: ScheduleSlot):
        gid = slot.group_id
        if not gid or gid == DISABLED_ID: return
        
        if self.hard_start <= slot.hour < self.hard_end:
            if gid in self.group_hard_hours:
                self.group_hard_hours[gid] += 1
            
        key = (gid, slot.date)
        self.group_daily_counts[key] = self.group_daily_counts.get(key, 0) + 1

    def update_slot(self, slot: ScheduleSlot, new_group_id: Optional[str]):
        old_gid = slot.group_id
        
        if old_gid and old_gid != DISABLED_ID:
            if self.hard_start <= slot.hour < self.hard_end:
                self.group_hard_hours[old_gid] -= 1
            key = (old_gid, slot.date)
            if key in self.group_daily_counts:
                self.group_daily_counts[key] -= 1

        slot.group_id = new_group_id
        
        if new_group_id and new_group_id != DISABLED_ID:
            if self.hard_start <= slot.hour < self.hard_end:
                self.group_hard_hours[new_group_id] += 1
            key = (new_group_id, slot.date)
            self.group_daily_counts[key] = self.group_daily_counts.get(key, 0) + 1

    def get_staffing_at(self, group: Group, date_str: str, hour: int) -> int:
        for exc in group.staffing_exceptions:
            try:
                dt = datetime.strptime(f"{date_str} {hour}:00", "%Y-%m-%d %H:%M")
                start_dt = datetime.strptime(f"{exc.start_date} {exc.start_hour}:00", "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(f"{exc.end_date} {exc.end_hour}:00", "%Y-%m-%d %H:%M")
                if start_dt <= dt < end_dt:
                    return exc.new_staffing_size
            except ValueError:
                pass
        return group.staffing_size if group.staffing_size is not None else 4 

    def get_group_consecutive_score(self, group_id: str) -> float:
        if group_id == DISABLED_ID: return 0
        group = self.groups.get(group_id)
        if not group: return 0
        
        score = 0
        current_seq = 0
        last_active_idx = -999
        
        for idx, (date_str, hour) in enumerate(self.time_points):
            current_staffing = self.get_staffing_at(group, date_str, hour)
            
            if current_staffing <= 2:
                desired_seq = 2
            else:
                desired_seq = max(2, current_staffing // 2)
            
            is_active = False
            for pos in [1, 2]:
                s = self.slot_map.get((date_str, hour, pos))
                if s and s.group_id == group_id:
                    is_active = True
                    break
            
            s_ref = self.slot_map.get((date_str, hour, 1))
            day_of_week = s_ref.day_of_week if s_ref else 0
            
            from shmirot_gdud.core.constraints.implementations import ActivityWindowConstraint
            for c in group.constraints:
                if isinstance(c, ActivityWindowConstraint):
                    for w in c.windows:
                        if w['day'] == day_of_week and w['start_hour'] <= hour < w['end_hour']:
                            is_active = True
                            break
            
            if is_active:
                if current_seq == 0 and last_active_idx != -999:
                    rest_time = idx - last_active_idx - 1
                    
                    if rest_time < 6:
                        score -= (6 - rest_time) * config.REST_PENALTY
                    elif rest_time < 16:
                        score -= config.SHORT_REST_PENALTY
                    elif rest_time >= 24:
                        score += config.LONG_REST_BONUS
                
                current_seq += 1
                last_active_idx = idx
            else:
                if current_seq > 0:
                    if current_seq <= desired_seq:
                        score += (current_seq * config.CONSECUTIVE_BONUS_PER_HOUR)
                    else:
                        excess = current_seq - desired_seq
                        score -= (excess ** config.CONSECUTIVE_PENALTY_EXPONENT) * config.CONSECUTIVE_PENALTY_MULTIPLIER
                    
                    current_seq = 0
                    
        return score

    def get_simultaneous_score(self) -> float:
        score = 0
        for date_str, hour in self.time_points:
            s1 = self.slot_map.get((date_str, hour, 1))
            s2 = self.slot_map.get((date_str, hour, 2))
            
            if s1 and s2 and s1.group_id and s2.group_id:
                if s1.group_id != DISABLED_ID and s2.group_id != DISABLED_ID:
                    if s1.group_id == s2.group_id:
                        score += config.SIMULTANEOUS_BONUS
        return score

class Scheduler:
    def __init__(self, groups: List[Group]):
        self.groups = groups
        self.schedule: Optional[Schedule] = None
        self.context: Optional[ScheduleContext] = None
        self.rule_usage = {} 

    def _get_group(self, group_id: Optional[str]) -> Optional[Group]:
        if not group_id or group_id == DISABLED_ID: return None
        return next((g for g in self.groups if g.id == group_id), None)

    def fill_schedule(self, schedule: Schedule) -> Schedule:
        self.schedule = schedule
        
        # Initialize Context
        self.context = ScheduleContext(slot_map={})
        for s in self.schedule.slots:
            self.context.slot_map[(s.date, s.hour, s.position)] = s
            
        # Initialize usage counters from existing assignments
        self.context.usage_counters = {}
        self.rule_usage = {}
        
        for s in self.schedule.slots:
            if s.group_id and s.group_id != DISABLED_ID:
                group = self._get_group(s.group_id)
                if group:
                    group.notify_assignment(s, self.context)
                    self._update_usage_for_slot(s, group, 1)

        available_groups = [g for g in self.groups if g.validate()]
        if not available_groups: return self.schedule

        empty_slots = [s for s in self.schedule.slots if s.group_id is None]
        filled_slots = [s for s in self.schedule.slots if s.group_id is not None and s.group_id != DISABLED_ID]
        
        if not empty_slots: return self.schedule

        total_slots_to_fill = len(empty_slots)
        
        start_date = datetime.strptime(self.schedule.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(self.schedule.end_date, "%Y-%m-%d")
        days_diff = (end_date - start_date).days + 1
        weeks_ratio = days_diff / 7.0
        
        fixed_quota_groups = [g for g in available_groups if g.weekly_guard_quota is not None]
        proportional_groups = [g for g in available_groups if g.weekly_guard_quota is None and g.staffing_size is not None]
        
        current_counts = {g.id: 0 for g in available_groups}
        for s in filled_slots:
            if s.group_id in current_counts:
                current_counts[s.group_id] += 1
        
        group_targets = {}
        fixed_slots_needed = 0
        for g in fixed_quota_groups:
            target = round(g.weekly_guard_quota * weeks_ratio)
            group_targets[g.id] = target
            fixed_slots_needed += max(0, target - current_counts[g.id])
            
        remaining_slots_for_prop = total_slots_to_fill - fixed_slots_needed
        total_staffing = sum(g.staffing_size for g in proportional_groups)
        
        if total_staffing > 0:
            for g in proportional_groups:
                share = (g.staffing_size / total_staffing) * remaining_slots_for_prop
                group_targets[g.id] = current_counts[g.id] + round(share)
        
        needed_sum = sum(max(0, group_targets.get(g.id, 0) - current_counts.get(g.id, 0)) for g in available_groups)
        diff = total_slots_to_fill - needed_sum
        if diff != 0:
            if proportional_groups: group_targets[proportional_groups[0].id] += diff
            elif fixed_quota_groups: group_targets[fixed_quota_groups[0].id] += diff

        random.shuffle(empty_slots)
        filled_in_loop = set()

        for slot in empty_slots:
            if slot in filled_in_loop: continue
            if slot.group_id is not None: continue

            other_slot = self.context.get_other_slot(slot)
            other_group_id = other_slot.group_id if other_slot and other_slot.group_id != DISABLED_ID else None
            
            self.context.other_group_id = other_group_id
            self.context.is_initial_fill = True
            
            selected_group = self._select_best_group(slot, available_groups, current_counts, group_targets)
            
            if selected_group:
                requires_coupling = self._check_coupling_requirement(selected_group, slot)
                
                if requires_coupling:
                    if not selected_group.can_guard_simultaneously:
                        continue

                    if other_slot and other_slot.group_id is None:
                        self._assign_slot(slot, selected_group)
                        self._assign_slot(other_slot, selected_group)
                        current_counts[selected_group.id] += 2
                        filled_in_loop.add(other_slot)
                    else:
                        pass
                else:
                    self._assign_slot(slot, selected_group)
                    current_counts[selected_group.id] += 1
        
        return self.schedule

    def _assign_slot(self, slot: ScheduleSlot, group: Group):
        slot.group_id = group.id
        group.notify_assignment(slot, self.context)
        self._update_usage_for_slot(slot, group, 1)

    def _update_usage_for_slot(self, slot: ScheduleSlot, group: Group, delta: int):
        for c_idx, constraint in enumerate(group.constraints):
            if isinstance(constraint, StaffingRuleConstraint):
                for r_idx, r in enumerate(constraint.rules):
                    if r['day'] == slot.day_of_week and r['start_hour'] <= slot.hour < r['end_hour']:
                        key = (group.id, c_idx, r_idx)
                        self.rule_usage[key] = self.rule_usage.get(key, 0) + delta

    def _check_coupling_requirement(self, group: Group, slot: ScheduleSlot) -> bool:
        for constraint in group.constraints:
            if isinstance(constraint, StaffingRuleConstraint):
                for r in constraint.rules:
                    if r['day'] == slot.day_of_week and r['start_hour'] <= slot.hour < r['end_hour']:
                        if r.get('force_coupling'):
                            return True
        return False

    def _select_best_group(self, slot: ScheduleSlot, groups: List[Group], current_counts: Dict[str, int], targets: Dict[str, int]) -> Optional[Group]:
        candidates = []
        
        for g in groups:
            if not g.is_available(slot, self.context): continue
            
            # Check staffing rules manually for initial fill (capacity/coupling)
            if not self._check_staffing_rules_initial(g, slot, self.context.other_group_id): continue
            
            other_group_id = getattr(self.context, 'other_group_id', None)
            if other_group_id == g.id and not g.can_guard_simultaneously: continue
            
            score = 0
            target = targets.get(g.id, 0)
            if target > 0:
                ratio = current_counts[g.id] / target
                if ratio >= 1.0: score -= 1000 
                else: score += (1.0 - ratio) * 100 
            else: score -= 2000
            
            score += g.calculate_score(slot, self.context) or 0
            
            if other_group_id == g.id and g.can_guard_simultaneously: score += 50
            
            candidates.append((score, g))
            
        candidates.sort(key=lambda x: x[0], reverse=True)
        if candidates: return candidates[0][1]
        return None

    def _check_staffing_rules_initial(self, group: Group, slot: ScheduleSlot, other_group_id: Optional[str]) -> bool:
        for c_idx, constraint in enumerate(group.constraints):
            if isinstance(constraint, StaffingRuleConstraint):
                for r_idx, r in enumerate(constraint.rules):
                    if r['day'] == slot.day_of_week and r['start_hour'] <= slot.hour < r['end_hour']:
                        if r.get('max_capacity') is not None:
                            key = (group.id, c_idx, r_idx)
                            current_usage = self.rule_usage.get(key, 0)
                            increment = 2 if (r.get('force_coupling') and other_group_id is None) else 1
                            if current_usage + increment > r['max_capacity']:
                                return False
                        if r.get('force_coupling'):
                            if not group.can_guard_simultaneously: return False
                            if other_group_id is not None and other_group_id != group.id: 
                                return False
        return True

    def improve_schedule(self, hard_start: int = 2, hard_end: int = 6, progress_callback: Optional[Callable[[float], None]] = None) -> Schedule:
        print("Starting improve_schedule (Best Improvement)...")
        start_time = time.time()
        
        if not self.schedule or not self.schedule.slots: return self.schedule
        
        mutable_slots = [s for s in self.schedule.slots if not s.is_locked and s.group_id != DISABLED_ID]
        if len(mutable_slots) < 2: return self.schedule

        # Initialize
        self.context = ScheduleContext(slot_map={})
        for s in self.schedule.slots:
            self.context.slot_map[(s.date, s.hour, s.position)] = s
            
        self.rule_usage = {}
        for g in self.groups:
            g.invalidate_cache()
            g._assigned_slots = set() 
            
        for s in self.schedule.slots:
            if s.group_id and s.group_id != DISABLED_ID:
                group = self._get_group(s.group_id)
                if group:
                    group.notify_assignment(s, self.context)
                    self._update_usage_for_slot(s, group, 1)

        state = ScheduleState(self.schedule, self.groups, hard_start, hard_end)
        
        # Group slots by time for block swaps
        slots_by_time = {}
        for s in mutable_slots:
            key = (s.date, s.hour)
            if key not in slots_by_time: slots_by_time[key] = []
            slots_by_time[key].append(s)
        time_keys = sorted(list(slots_by_time.keys()))
        
        current_total_score = self._calculate_global_score(state)
        print(f"Initial Score: {current_total_score}")
        
        num_times = len(time_keys)
        
        for i in range(num_times):
            t1_key = time_keys[i]
            slots1 = slots_by_time[t1_key]
            
            if progress_callback:
                p = (i / num_times) * 100
                progress_callback(p)
            
            best_move = None 
            best_score_diff = 0
            
            for j in range(i + 1, num_times):
                t2_key = time_keys[j]
                slots2 = slots_by_time[t2_key]
                
                moves = []
                
                # 1. Block Swap
                if len(slots1) == 2 and len(slots2) == 2:
                    moves.append(('block', [(slots1[0], slots2[0]), (slots1[1], slots2[1])]))
                
                # 2. Single Swaps
                for s1 in slots1:
                    for s2 in slots2:
                        moves.append(('single', [(s1, s2)]))
                
                for move_type, swap_pairs in moves:
                    if self._try_apply_move(swap_pairs):
                        new_score = self._calculate_global_score(state)
                        diff = new_score - current_total_score
                        
                        if diff > best_score_diff:
                            best_score_diff = diff
                            best_move = (move_type, swap_pairs)
                        
                        self._revert_move(swap_pairs)
                        for s1, s2 in swap_pairs:
                            state.update_slot(s1, s1.group_id)
                            state.update_slot(s2, s2.group_id)

            if best_move:
                move_type, swap_pairs = best_move
                print(f"  Found improvement at {t1_key}: +{best_score_diff:.2f} ({move_type})")
                
                self._apply_move_permanent(swap_pairs, state)
                current_total_score += best_score_diff
        
        if progress_callback: progress_callback(100)
        print(f"Finished in {time.time() - start_time:.2f}s. Final Score: {current_total_score}")
        return self.schedule

    def _try_apply_move(self, swap_pairs: List[Tuple[ScheduleSlot, ScheduleSlot]]) -> bool:
        # Decrement usage
        for s1, s2 in swap_pairs:
            g1 = self._get_group(s1.group_id)
            g2 = self._get_group(s2.group_id)
            if g1: 
                g1.notify_removal(s1, self.context)
                self._update_usage_for_slot(s1, g1, -1)
            if g2: 
                g2.notify_removal(s2, self.context)
                self._update_usage_for_slot(s2, g2, -1)
            
        # Check validity
        valid = True
        
        for s1, s2 in swap_pairs:
            # s1 will get g2, s2 will get g1
            g1 = self._get_group(s1.group_id) # Original group at s1
            g2 = self._get_group(s2.group_id) # Original group at s2
            
            # Check g1 at s2
            if g1:
                # Need to know what's in other_s2 AFTER swap
                other_s2 = self.context.get_other_slot(s2)
                other_gid_at_s2 = other_s2.group_id if other_s2 else None
                
                # If other_s2 is part of swap (block swap), find its new group
                for swap_a, swap_b in swap_pairs:
                    if other_s2 == swap_a: other_gid_at_s2 = swap_b.group_id
                    elif other_s2 == swap_b: other_gid_at_s2 = swap_a.group_id
                
                self.context.other_group_id = other_gid_at_s2
                self.context.group_id = g1.id
                
                if not g1.is_available(s2, self.context): valid = False
                if not self._check_staffing_rules_swap(g1, s1, s2): valid = False

            # Check g2 at s1
            if g2:
                other_s1 = self.context.get_other_slot(s1)
                other_gid_at_s1 = other_s1.group_id if other_s1 else None
                
                for swap_a, swap_b in swap_pairs:
                    if other_s1 == swap_a: other_gid_at_s1 = swap_b.group_id
                    elif other_s1 == swap_b: other_gid_at_s1 = swap_a.group_id
                
                self.context.other_group_id = other_gid_at_s1
                self.context.group_id = g2.id
                
                if not g2.is_available(s1, self.context): valid = False
                if not self._check_staffing_rules_swap(g2, s2, s1): valid = False
        
        if valid:
            # Apply swap
            for s1, s2 in swap_pairs:
                g1_id = s1.group_id
                g2_id = s2.group_id
                s1.group_id = g2_id
                s2.group_id = g1_id
                
                g1 = self._get_group(g1_id)
                g2 = self._get_group(g2_id)
                if g1: 
                    g1.notify_assignment(s2, self.context)
                    self._update_usage_for_slot(s2, g1, 1)
                if g2: 
                    g2.notify_assignment(s1, self.context)
                    self._update_usage_for_slot(s1, g2, 1)
            return True
        else:
            # Restore usage (Revert removal)
            for s1, s2 in swap_pairs:
                g1 = self._get_group(s1.group_id)
                g2 = self._get_group(s2.group_id)
                if g1: 
                    g1.notify_assignment(s1, self.context)
                    self._update_usage_for_slot(s1, g1, 1)
                if g2: 
                    g2.notify_assignment(s2, self.context)
                    self._update_usage_for_slot(s2, g2, 1)
            return False

    def _revert_move(self, swap_pairs: List[Tuple[ScheduleSlot, ScheduleSlot]]):
        for s1, s2 in swap_pairs:
            g2 = self._get_group(s1.group_id) # Currently at s1
            g1 = self._get_group(s2.group_id) # Currently at s2
            
            if g2: 
                g2.notify_removal(s1, self.context)
                self._update_usage_for_slot(s1, g2, -1)
            if g1: 
                g1.notify_removal(s2, self.context)
                self._update_usage_for_slot(s2, g1, -1)
            
            # Swap back
            temp = s1.group_id
            s1.group_id = s2.group_id
            s2.group_id = temp
            
            if g1: 
                g1.notify_assignment(s1, self.context)
                self._update_usage_for_slot(s1, g1, 1)
            if g2: 
                g2.notify_assignment(s2, self.context)
                self._update_usage_for_slot(s2, g2, 1)

    def _apply_move_permanent(self, swap_pairs: List[Tuple[ScheduleSlot, ScheduleSlot]], state: ScheduleState):
        # We assume move was reverted, so we apply it again
        for s1, s2 in swap_pairs:
            g1 = self._get_group(s1.group_id)
            g2 = self._get_group(s2.group_id)
            
            if g1: 
                g1.notify_removal(s1, self.context)
                self._update_usage_for_slot(s1, g1, -1)
            if g2: 
                g2.notify_removal(s2, self.context)
                self._update_usage_for_slot(s2, g2, -1)
            
            temp = s1.group_id
            s1.group_id = s2.group_id
            s2.group_id = temp
            
            if g1: 
                g1.notify_assignment(s2, self.context)
                self._update_usage_for_slot(s2, g1, 1)
            if g2: 
                g2.notify_assignment(s1, self.context)
                self._update_usage_for_slot(s1, g2, 1)
            
            state.update_slot(s1, s1.group_id)
            state.update_slot(s2, s2.group_id)

    def _check_staffing_rules_swap(self, group: Group, source_slot: ScheduleSlot, target_slot: ScheduleSlot) -> bool:
        for c_idx, constraint in enumerate(group.constraints):
            if isinstance(constraint, StaffingRuleConstraint):
                for r_idx, r in enumerate(constraint.rules):
                    if r['day'] == target_slot.day_of_week and r['start_hour'] <= target_slot.hour < r['end_hour']:
                        if r.get('max_capacity') is not None:
                            key = (group.id, c_idx, r_idx)
                            current_usage = self.rule_usage.get(key, 0)
                            source_in_rule = (r['day'] == source_slot.day_of_week and r['start_hour'] <= source_slot.hour < r['end_hour'])
                            new_usage = current_usage
                            if not source_in_rule:
                                new_usage += 1
                            if new_usage > r['max_capacity']:
                                return False
                        if r.get('force_coupling'):
                            if not group.can_guard_simultaneously: return False
                            other = self.context.get_other_slot(target_slot)
                            other_gid = getattr(self.context, 'other_group_id', None)
                            if other_gid is None and other: other_gid = other.group_id
                            
                            if other_gid != group.id:
                                return False
        return True

    def _calculate_global_score(self, state: ScheduleState) -> float:
        score = 0
        for g in self.groups:
            score += g.get_score(self.context)
        score += state.get_simultaneous_score()
        return score

    def validate_schedule(self) -> List[str]:
        errors = []
        return errors
