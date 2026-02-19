from typing import List, Dict, Optional, Tuple, Callable, Set
from .models import Group, Schedule, ScheduleSlot, TimeWindow
from .config import config
import random
import math
import time
from datetime import datetime, timedelta

DISABLED_ID = "DISABLED"

class ScheduleState:
    """
    Helper class to track the state of the schedule efficiently for scoring.
    """
    def __init__(self, schedule: Schedule, groups: List[Group], hard_start: int, hard_end: int):
        self.schedule = schedule
        self.groups = {g.id: g for g in groups}
        self.hard_start = hard_start
        self.hard_end = hard_end
        
        # Fast lookup
        self.slot_map: Dict[Tuple[str, int, int], ScheduleSlot] = {}
        for s in schedule.slots:
            self.slot_map[(s.date, s.hour, s.position)] = s
            
        # Pre-calculate chronological order of slots
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
        
        # Initialize counters
        self.group_hard_hours = {g_id: 0 for g_id in self.groups}
        self.group_daily_counts = {} # (g_id, date) -> count
        
        # Calculate initial state
        for s in schedule.slots:
            if not s.group_id or s.group_id == DISABLED_ID: continue
            self._add_to_state(s)

    def _add_to_state(self, slot: ScheduleSlot):
        gid = slot.group_id
        if not gid or gid == DISABLED_ID: return
        
        # Hard hours
        if self.hard_start <= slot.hour < self.hard_end:
            if gid in self.group_hard_hours:
                self.group_hard_hours[gid] += 1
            
        # Daily counts
        key = (gid, slot.date)
        self.group_daily_counts[key] = self.group_daily_counts.get(key, 0) + 1

    def get_group_consecutive_score(self, group_id: str) -> float:
        if group_id == DISABLED_ID: return 0
        
        group = self.groups.get(group_id)
        if not group: return 0
        
        score = 0
        max_consecutive = group.staffing_size if group.staffing_size else 4
        if max_consecutive < 2: max_consecutive = 2
        
        current_seq = 0
        last_active_idx = -999
        
        for idx, (date_str, hour) in enumerate(self.time_points):
            is_active = False
            for pos in [1, 2]:
                s = self.slot_map.get((date_str, hour, pos))
                if s and s.group_id == group_id:
                    is_active = True
                    break
            
            # Check activity window conflict
            s_ref = self.slot_map.get((date_str, hour, 1))
            day_of_week = s_ref.day_of_week if s_ref else 0
            
            for rule in group.primary_activity_windows:
                if rule.day == day_of_week and rule.start_hour <= hour < rule.end_hour:
                    is_active = True
                    break
            
            if is_active:
                if current_seq == 0 and last_active_idx != -999:
                    rest_time = idx - last_active_idx - 1
                    if rest_time < 6:
                        # Penalty: Subtract from score
                        score -= (6 - rest_time) * config.REST_PENALTY
                
                current_seq += 1
                last_active_idx = idx
            else:
                if current_seq > 0:
                    if current_seq <= max_consecutive:
                        # Bonus: Add to score
                        score += (current_seq * config.CONSECUTIVE_BONUS_PER_HOUR)
                    else:
                        # Penalty: Subtract from score
                        excess = current_seq - max_consecutive
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
                        # Bonus: Add to score
                        score += config.SIMULTANEOUS_BONUS
        return score

class Scheduler:
    def __init__(self, groups: List[Group]):
        self.groups = groups
        self.schedule: Optional[Schedule] = None

    def fill_schedule(self, schedule: Schedule) -> Schedule:
        self.schedule = schedule
        
        available_groups = [g for g in self.groups if g.validate()]
        if not available_groups:
            return self.schedule

        empty_slots = [s for s in self.schedule.slots if s.group_id is None]
        filled_slots = [s for s in self.schedule.slots if s.group_id is not None and s.group_id != DISABLED_ID]
        
        if not empty_slots:
            return self.schedule

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
            if proportional_groups:
                group_targets[proportional_groups[0].id] += diff
            elif fixed_quota_groups:
                group_targets[fixed_quota_groups[0].id] += diff

        random.shuffle(empty_slots)
        
        for slot in empty_slots:
            other_slot = self._get_other_slot(slot)
            other_group_id = other_slot.group_id if other_slot and other_slot.group_id != DISABLED_ID else None
            
            selected_group = self._select_best_group(
                slot, 
                available_groups, 
                current_counts, 
                group_targets, 
                other_group_id
            )
            
            if selected_group:
                slot.group_id = selected_group.id
                current_counts[selected_group.id] += 1
                
        return self.schedule

    def improve_schedule(self, hard_start: int = 2, hard_end: int = 6, progress_callback: Optional[Callable[[float], None]] = None) -> Schedule:
        print("Starting improve_schedule...")
        start_time = time.time()
        
        if not self.schedule or not self.schedule.slots:
            return self.schedule
            
        mutable_slots = [s for s in self.schedule.slots if not s.is_locked and s.group_id != DISABLED_ID]
        if len(mutable_slots) < 2:
            return self.schedule

        self.slot_map = {}
        for s in self.schedule.slots:
            self.slot_map[(s.date, s.hour, s.position)] = s

        total_hard_slots = 0
        for s in self.schedule.slots:
            if hard_start <= s.hour < hard_end:
                total_hard_slots += 1
                
        available_groups = [g for g in self.groups if g.validate()]
        hard_targets = self._calculate_hard_targets(available_groups, total_hard_slots)

        state = ScheduleState(self.schedule, self.groups, hard_start, hard_end)
        
        current_global_score = self._calculate_global_score(state)
        print(f"Initial Score: {current_global_score}")

        max_passes = 5
        n = len(mutable_slots)
        print(f"Mutable slots: {n}, Max passes: {max_passes}")
        
        for pass_num in range(max_passes):
            print(f"--- Pass {pass_num + 1}/{max_passes} ---")
            improved = False
            
            for i in range(n):
                if i % 20 == 0 and progress_callback:
                    p = (pass_num + (i / n) * 0.5) / max_passes * 100
                    progress_callback(p)

                for j in range(i + 1, n):
                    s1 = mutable_slots[i]
                    s2 = mutable_slots[j]
                    
                    if s1.group_id == s2.group_id: continue
                    
                    g1_id = s1.group_id
                    g2_id = s2.group_id
                    
                    if not self._is_swap_valid(s1, self._get_group(g1_id), s2, self._get_group(g2_id)):
                        continue

                    score_g1_before = state.get_group_consecutive_score(g1_id)
                    score_g2_before = state.get_group_consecutive_score(g2_id)
                    
                    sim_delta = self._calculate_simultaneous_delta(s1, s2, g1_id, g2_id)
                    
                    s1.group_id, s2.group_id = g2_id, g1_id
                    
                    score_g1_after = state.get_group_consecutive_score(g1_id)
                    score_g2_after = state.get_group_consecutive_score(g2_id)
                    
                    local_delta = self._calculate_simple_local_delta(s1, s2, g1_id, g2_id, hard_start, hard_end, hard_targets)
                    
                    consecutive_delta = (score_g1_after + score_g2_after) - (score_g1_before + score_g2_before)
                    
                    total_delta = local_delta + consecutive_delta + sim_delta
                    
                    # Maximization: We want delta > 0 (Score increased)
                    if total_delta > 0:
                        improved = True
                    else:
                        s1.group_id, s2.group_id = g1_id, g2_id
            
            if not improved:
                print("No improvement in this pass, stopping early.")
                break
        
        if progress_callback:
            progress_callback(100)
            
        total_time = time.time() - start_time
        print(f"Finished improve_schedule in {total_time:.2f}s.")
        
        if hasattr(self, 'slot_map'):
            del self.slot_map
            
        return self.schedule

    def _calculate_simultaneous_delta(self, s1: ScheduleSlot, s2: ScheduleSlot, old_g1_id: str, old_g2_id: str) -> float:
        delta = 0
        
        other_s1 = self._get_other_slot_fast(s1)
        if other_s1:
            # Before: s1=g1. If other=g1, we had bonus. Now we lose it.
            if other_s1.group_id == old_g1_id: delta -= config.SIMULTANEOUS_BONUS 
            # After: s1=g2. If other=g2, we gain bonus.
            other_gid_after = old_g1_id if other_s1 == s2 else other_s1.group_id
            if other_gid_after == old_g2_id: delta += config.SIMULTANEOUS_BONUS 
            
        if other_s1 != s2:
            other_s2 = self._get_other_slot_fast(s2)
            if other_s2:
                if other_s2.group_id == old_g2_id: delta -= config.SIMULTANEOUS_BONUS 
                if other_s2.group_id == old_g1_id: delta += config.SIMULTANEOUS_BONUS 
                
        return delta

    def _calculate_hard_targets(self, groups: List[Group], total_hard_slots: int) -> Dict[str, float]:
        targets = {}
        total_weight = 0
        for g in groups:
            w = g.staffing_size if g.staffing_size else (g.weekly_guard_quota if g.weekly_guard_quota else 1)
            total_weight += w
        if total_weight == 0: return {}
        for g in groups:
            w = g.staffing_size if g.staffing_size else (g.weekly_guard_quota if g.weekly_guard_quota else 1)
            targets[g.id] = (w / total_weight) * total_hard_slots
        return targets

    def _calculate_simple_local_delta(self, s1: ScheduleSlot, s2: ScheduleSlot, old_g1_id: str, old_g2_id: str, hard_start: int, hard_end: int, hard_targets: Dict[str, float]) -> float:
        score_s1_new = self._get_single_slot_score(s1, old_g2_id, hard_start, hard_end, hard_targets)
        score_s1_old = self._get_single_slot_score(s1, old_g1_id, hard_start, hard_end, hard_targets)
        
        score_s2_new = self._get_single_slot_score(s2, old_g1_id, hard_start, hard_end, hard_targets)
        score_s2_old = self._get_single_slot_score(s2, old_g2_id, hard_start, hard_end, hard_targets)
        
        return (score_s1_new + score_s2_new) - (score_s1_old + score_s2_old)

    def _get_single_slot_score(self, slot: ScheduleSlot, group_id: str, hard_start: int, hard_end: int, hard_targets: Dict[str, float]) -> float:
        if not group_id: return 0
        score = 0
        group = self._get_group(group_id)
        
        # Activity Window Penalty
        if self._is_activity_window(group, slot.day_of_week, slot.hour):
            score -= config.ACTIVITY_WINDOW_PENALTY
            
        # Hard Hours Balance Penalty
        if hard_start <= slot.hour < hard_end:
            target = hard_targets.get(group_id, 1.0)
            if target > 0:
                score -= (100 / target) 
            else:
                score -= config.HARD_HOUR_PENALTY_BASE
                
        # Distribution Penalty
        same_day_count = self._count_group_on_day(group.id, slot.date)
        if same_day_count > 2: 
             score -= (same_day_count - 2) * config.SAME_DAY_PENALTY
             
        return score

    def _count_group_on_day(self, group_id: str, date_str: str) -> int:
        count = 0
        for h in range(24):
            for pos in [1, 2]:
                s = self._get_slot_fast(date_str, h, pos)
                if s and s.group_id == group_id:
                    count += 1
        return count

    def _get_slot_fast(self, date: str, hour: int, position: int) -> Optional[ScheduleSlot]:
        if hasattr(self, 'slot_map'):
            return self.slot_map.get((date, hour, position))
        return self.schedule.get_slot(date, hour, position)
        
    def _get_other_slot_fast(self, slot: ScheduleSlot) -> Optional[ScheduleSlot]:
        other_pos = 2 if slot.position == 1 else 1
        return self._get_slot_fast(slot.date, slot.hour, other_pos)

    def _is_swap_valid(self, s1: ScheduleSlot, g1: Optional[Group], s2: ScheduleSlot, g2: Optional[Group]) -> bool:
        if g1 and not self._is_group_available(g1, s2.day_of_week, s2.hour, s2.date): return False
        if g2 and not self._is_group_available(g2, s1.day_of_week, s1.hour, s1.date): return False
        
        if g1:
            other_s2 = self._get_other_slot_fast(s2)
            other_gid = other_s2.group_id if other_s2 else None
            if other_s2 == s1: other_gid = g2.id if g2 else None 
            
            if other_gid == g1.id and not g1.can_guard_simultaneously: return False
            
        if g2:
            other_s1 = self._get_other_slot_fast(s1)
            other_gid = other_s1.group_id if other_s1 else None
            if other_s1 == s2: other_gid = g1.id if g1 else None 
            
            if other_gid == g2.id and not g2.can_guard_simultaneously: return False
            
        return True

    def _get_other_slot(self, slot: ScheduleSlot) -> Optional[ScheduleSlot]:
        other_pos = 2 if slot.position == 1 else 1
        return self.schedule.get_slot(slot.date, slot.hour, other_pos)

    def _get_group(self, group_id: Optional[str]) -> Optional[Group]:
        if not group_id or group_id == DISABLED_ID: return None
        return next((g for g in self.groups if g.id == group_id), None)

    def _select_best_group(self, slot: ScheduleSlot, groups: List[Group], current_counts: Dict[str, int], targets: Dict[str, int], other_group_id: Optional[str]) -> Optional[Group]:
        candidates = []
        for g in groups:
            if not self._is_group_available(g, slot.day_of_week, slot.hour, slot.date): continue
            if other_group_id == g.id and not g.can_guard_simultaneously: continue
            
            score = 0
            target = targets.get(g.id, 0)
            if target > 0:
                ratio = current_counts[g.id] / target
                if ratio >= 1.0: score -= 1000 # Penalty
                else: score += (1.0 - ratio) * 100 # Bonus for being under target
            else: score -= 2000
            
            if self._is_activity_window(g, slot.day_of_week, slot.hour): score -= 500
            if other_group_id == g.id and g.can_guard_simultaneously: score += 50
            candidates.append((score, g))
            
        # Sort descending (Higher score is better)
        candidates.sort(key=lambda x: x[0], reverse=True)
        if candidates: return candidates[0][1]
        return None

    def _is_group_available(self, group: Group, day: int, hour: int, date_str: str) -> bool:
        has_positive = False
        allowed = False
        for c in group.date_constraints:
            if date_str in c.dates:
                if not c.is_available:
                    if c.start_hour <= hour < c.end_hour: return False
                else:
                    has_positive = True
                    if c.start_hour <= hour < c.end_hour: allowed = True
        
        if has_positive: return allowed

        for rule in group.hard_unavailability_rules:
            if rule.day == day and rule.start_hour <= hour < rule.end_hour: return False
        return True

    def _is_activity_window(self, group: Group, day: int, hour: int) -> bool:
        for rule in group.primary_activity_windows:
            if rule.day == day and rule.start_hour <= hour < rule.end_hour: return True
        return False

    def _calculate_global_score(self, state: ScheduleState) -> float:
        score = 0
        for g in self.groups:
            score += state.get_group_consecutive_score(g.id)
        score += state.get_simultaneous_score()
        return score

    def validate_schedule(self) -> List[str]:
        errors = []
        for slot in self.schedule.slots:
            if slot.group_id and slot.group_id != DISABLED_ID:
                group = self._get_group(slot.group_id)
                if not group: continue
                if not self._is_group_available(group, slot.day_of_week, slot.hour, slot.date):
                    errors.append(f"Group {group.name} unavailable at {slot.date} {slot.hour}:00")
        return errors
