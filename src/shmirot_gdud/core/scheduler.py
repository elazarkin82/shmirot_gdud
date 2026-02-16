from typing import List, Dict, Optional, Tuple
from .models import Group, WeeklySchedule, ScheduleSlot, TimeWindow, ScheduleRange
import random
import math

class Scheduler:
    def __init__(self, groups: List[Group]):
        self.groups = groups
        self.schedule = WeeklySchedule(week_start_date="2023-01-01") # Placeholder date

    def generate_schedule(self, active_range: Optional[ScheduleRange] = None) -> WeeklySchedule:
        # Initialize empty schedule
        self.schedule.slots = []
        self.schedule.active_range = active_range
        
        available_groups = [g for g in self.groups if g.validate()]
        if not available_groups:
            return self.schedule

        # Determine active slots
        time_slots = []
        if active_range:
            # Linearize time to hours from start of week (0 to 167)
            start_linear = active_range.start_day * 24 + active_range.start_hour
            end_linear = active_range.end_day * 24 + active_range.end_hour
            
            for t in range(start_linear, end_linear):
                day = (t // 24) % 7
                hour = t % 24
                time_slots.append((day, hour))
        else:
            # Full week
            for day in range(7):
                for hour in range(24):
                    time_slots.append((day, hour))

        total_slots = len(time_slots) * 2 # 2 positions per slot
        
        # Calculate scaling factor for quotas
        full_week_slots = 7 * 24 * 2
        quota_scale = total_slots / full_week_slots if full_week_slots > 0 else 0

        # Calculate target quotas
        fixed_quota_groups = [g for g in available_groups if g.weekly_guard_quota is not None]
        proportional_groups = [g for g in available_groups if g.weekly_guard_quota is None and g.staffing_size is not None]
        
        # Scale fixed quotas
        fixed_slots_needed = sum(round(g.weekly_guard_quota * quota_scale) for g in fixed_quota_groups)
        remaining_slots = total_slots - fixed_slots_needed
        
        total_staffing = sum(g.staffing_size for g in proportional_groups)
        
        group_targets = {}
        for g in fixed_quota_groups:
            group_targets[g.id] = round(g.weekly_guard_quota * quota_scale)
            
        if total_staffing > 0:
            for g in proportional_groups:
                share = (g.staffing_size / total_staffing) * remaining_slots
                group_targets[g.id] = round(share)
        
        # Adjust rounding errors
        current_total = sum(group_targets.values())
        diff = total_slots - current_total
        if diff != 0 and proportional_groups:
             group_targets[proportional_groups[0].id] += diff
        elif diff != 0 and fixed_quota_groups:
             # Fallback if no proportional groups
             group_targets[fixed_quota_groups[0].id] += diff

        # Shuffle time slots to distribute "bad" hours fairly
        random.shuffle(time_slots)
        
        current_counts = {g.id: 0 for g in available_groups}
        
        # Fill slots
        for day, hour in time_slots:
            # Try to fill Position 1
            g1 = self._select_best_group(day, hour, available_groups, current_counts, group_targets)
            if g1:
                self.schedule.slots.append(ScheduleSlot(day, hour, 1, g1.id))
                current_counts[g1.id] += 1
            
            # Try to fill Position 2
            # Preference: Same group if possible and quota allows, otherwise best other group
            g2 = None
            if g1 and self._can_assign(g1, day, hour, current_counts, group_targets):
                 # Check if we want to double up (Soft constraint: prefer same group)
                 # But only if it doesn't violate hard constraints or activity windows too badly
                 # AND if the group allows simultaneous guarding
                 if g1.can_guard_simultaneously:
                     g2 = g1
            
            if not g2:
                g2 = self._select_best_group(day, hour, available_groups, current_counts, group_targets, exclude_group_id=g1.id if g1 else None)
            
            if g2:
                self.schedule.slots.append(ScheduleSlot(day, hour, 2, g2.id))
                current_counts[g2.id] += 1
                
        # Run improvement immediately after generation for better initial result
        self.improve_schedule()
        
        return self.schedule

    def improve_schedule(self) -> WeeklySchedule:
        """
        Runs a Hill Climbing optimization to improve the schedule quality.
        Swaps slots to minimize soft constraint violations.
        """
        if not self.schedule or not self.schedule.slots:
            return self.schedule
            
        iterations = 1000
        
        # Pre-calculate current score (optional, but good for tracking)
        current_score = self._calculate_schedule_score()
        
        # Group slots by (day, hour) for block swapping
        slots_by_time = {}
        for slot in self.schedule.slots:
            key = (slot.day, slot.hour)
            if key not in slots_by_time:
                slots_by_time[key] = []
            slots_by_time[key].append(slot)
            
        time_keys = list(slots_by_time.keys())
        if len(time_keys) < 2:
            return self.schedule

        for _ in range(iterations):
            # Decide move type: 50% Single Swap, 50% Block Swap
            move_type = random.choice(['single', 'block'])
            
            if move_type == 'single':
                self._try_single_swap(current_score)
            else:
                self._try_block_swap(current_score, slots_by_time, time_keys)
                
        return self.schedule

    def _get_linear_time(self, day: int, hour: int) -> int:
        return day * 24 + hour

    def _try_single_swap(self, current_score):
        # Pick first random slot
        idx1 = random.randint(0, len(self.schedule.slots) - 1)
        slot1 = self.schedule.slots[idx1]
        t1 = self._get_linear_time(slot1.day, slot1.hour)
        
        # Filter candidates within 12 hours range
        candidates_indices = []
        for i, s in enumerate(self.schedule.slots):
            if i == idx1: continue
            t2 = self._get_linear_time(s.day, s.hour)
            if abs(t1 - t2) <= 12:
                candidates_indices.append(i)
        
        if not candidates_indices:
            return

        idx2 = random.choice(candidates_indices)
        slot2 = self.schedule.slots[idx2]
        
        # Get groups
        g1 = next((g for g in self.groups if g.id == slot1.group_id), None)
        g2 = next((g for g in self.groups if g.id == slot2.group_id), None)
        
        # Check if swap is valid (Hard constraints)
        if not self._is_swap_valid(slot1, g1, slot2, g2):
            return
            
        # Calculate score delta
        score_before = self._calculate_local_score(slot1, g1) + self._calculate_local_score(slot2, g2)
        
        # Swap in memory
        slot1.group_id, slot2.group_id = slot2.group_id, slot1.group_id
        
        # Recalculate local score
        score_after = self._calculate_local_score(slot1, g2) + self._calculate_local_score(slot2, g1)
        
        # Decide
        if score_after < score_before:
            # Keep swap (improvement)
            pass
        else:
            # Revert swap
            slot1.group_id, slot2.group_id = slot2.group_id, slot1.group_id

    def _try_block_swap(self, current_score, slots_by_time, time_keys):
        # Pick first random time
        t1_key = random.choice(time_keys)
        t1_linear = self._get_linear_time(*t1_key)
        
        # Filter candidates within 12 hours range
        candidates_keys = []
        for k in time_keys:
            if k == t1_key: continue
            t2_linear = self._get_linear_time(*k)
            if abs(t1_linear - t2_linear) <= 12:
                candidates_keys.append(k)
                
        if not candidates_keys:
            return
            
        t2_key = random.choice(candidates_keys)
        
        slots1 = slots_by_time[t1_key]
        slots2 = slots_by_time[t2_key]
        
        # Collect groups involved
        groups1 = [next((g for g in self.groups if g.id == s.group_id), None) for s in slots1]
        groups2 = [next((g for g in self.groups if g.id == s.group_id), None) for s in slots2]
        
        # Check validity
        day1, hour1 = t1_key
        day2, hour2 = t2_key
        
        # Check groups1 moving to t2
        for g in groups1:
            if g and not self._is_group_available(g, day2, hour2):
                return
        
        # Check groups2 moving to t1
        for g in groups2:
            if g and not self._is_group_available(g, day1, hour1):
                return
                
        # Calculate score before
        score_before = 0
        for i, s in enumerate(slots1): score_before += self._calculate_local_score(s, groups1[i])
        for i, s in enumerate(slots2): score_before += self._calculate_local_score(s, groups2[i])
        
        # Perform Swap
        min_len = min(len(slots1), len(slots2))
        
        for i in range(min_len):
            slots1[i].group_id, slots2[i].group_id = slots2[i].group_id, slots1[i].group_id
            
        # Calculate score after
        score_after = 0
        for i, s in enumerate(slots1): 
            g = groups2[i] if i < len(groups2) else None
            score_after += self._calculate_local_score(s, g)
            
        for i, s in enumerate(slots2):
            g = groups1[i] if i < len(groups1) else None
            score_after += self._calculate_local_score(s, g)
            
        # Decide
        if score_after < score_before:
            # Keep swap
            pass
        else:
            # Revert
            for i in range(min_len):
                slots1[i].group_id, slots2[i].group_id = slots2[i].group_id, slots1[i].group_id

    def _is_swap_valid(self, slot1: ScheduleSlot, g1: Optional[Group], slot2: ScheduleSlot, g2: Optional[Group]) -> bool:
        # Check if g1 can be in slot2
        if g1 and not self._is_group_available(g1, slot2.day, slot2.hour):
            return False
            
        # Check if g2 can be in slot1
        if g2 and not self._is_group_available(g2, slot1.day, slot1.hour):
            return False
            
        # Check simultaneous constraint for slot1 (after swap: contains g2)
        if g2:
            other_in_slot1 = self._get_other_group_in_slot(slot1)
            if other_in_slot1 and other_in_slot1.id == g2.id and not g2.can_guard_simultaneously:
                return False
                
        # Check simultaneous constraint for slot2 (after swap: contains g1)
        if g1:
            other_in_slot2 = self._get_other_group_in_slot(slot2)
            if other_in_slot2 and other_in_slot2.id == g1.id and not g1.can_guard_simultaneously:
                return False
                
        return True

    def _get_other_group_in_slot(self, slot: ScheduleSlot) -> Optional[Group]:
        # Find the other position in the same day/hour
        other_pos = 2 if slot.position == 1 else 1
        other_slot = next((s for s in self.schedule.slots if s.day == slot.day and s.hour == slot.hour and s.position == other_pos), None)
        if other_slot and other_slot.group_id:
            return next((g for g in self.groups if g.id == other_slot.group_id), None)
        return None

    def _calculate_schedule_score(self) -> float:
        score = 0
        for slot in self.schedule.slots:
            group = next((g for g in self.groups if g.id == slot.group_id), None)
            score += self._calculate_local_score(slot, group)
        return score

    def _calculate_local_score(self, slot: ScheduleSlot, group: Optional[Group]) -> float:
        if not group: return 0
        
        score = 0
        
        # Penalty: Activity Window
        if self._is_activity_window(group, slot.day, slot.hour):
            score += 100
            
        # Bonus: Same group in both positions (Simultaneous)
        # We want to encourage this if allowed
        other_group = self._get_other_group_in_slot(slot)
        if other_group and other_group.id == group.id:
            score -= 50 # Good!
        elif other_group:
            score += 10 # Slight penalty for mixing groups
            
        # Penalty: Consecutive shifts (Simple check)
        # This is expensive to check globally in local score, but we can check adjacent slots
        # For now, let's stick to simple criteria
        
        return score

    def _can_assign(self, group: Group, day: int, hour: int, current_counts: Dict[str, int], targets: Dict[str, int]) -> bool:
        if not self._is_group_available(group, day, hour):
            return False
        if current_counts[group.id] >= targets.get(group.id, 0):
            return False
        return True

    def _select_best_group(self, day: int, hour: int, groups: List[Group], current_counts: Dict[str, int], targets: Dict[str, int], exclude_group_id: Optional[str] = None) -> Optional[Group]:
        candidates = []
        
        for g in groups:
            if exclude_group_id and g.id == exclude_group_id:
                continue
            
            if not self._is_group_available(g, day, hour):
                continue
            
            # Score candidates
            # Lower score is better
            score = 0
            
            # 1. Quota satisfaction (Primary)
            # We want groups that are far from their target to be picked first
            target = targets.get(g.id, 0)
            if target > 0:
                ratio = current_counts[g.id] / target
                if ratio >= 1.0:
                    score += 1000 # Penalty for exceeding quota
                else:
                    score += ratio * 100 # 0 to 100 based on progress
            else:
                score += 2000 # No target?
            
            # 2. Activity Windows (Secondary)
            if self._is_activity_window(g, day, hour):
                score += 500 # Big penalty for activity window
                
            candidates.append((score, g))
            
        candidates.sort(key=lambda x: x[0])
        
        if candidates:
            return candidates[0][1]
        
        # If no candidates found (e.g. everyone exceeded quota or unavailable), 
        # try to find ANY available group ignoring quota (but respecting unavailability)
        for g in groups:
            if exclude_group_id and g.id == exclude_group_id: continue
            if self._is_group_available(g, day, hour):
                return g
                
        return None

    def _is_group_available(self, group: Group, day: int, hour: int) -> bool:
        for rule in group.hard_unavailability_rules:
            if rule.day == day:
                 if rule.start_hour <= hour < rule.end_hour:
                     return False
        return True

    def _is_activity_window(self, group: Group, day: int, hour: int) -> bool:
        for rule in group.primary_activity_windows:
            if rule.day == day:
                 if rule.start_hour <= hour < rule.end_hour:
                     return True
        return False

    def validate_schedule(self) -> List[str]:
        errors = []
        group_counts = {}
        
        # Map slots by (day, hour) to check simultaneous guarding
        slots_by_time = {}
        
        for slot in self.schedule.slots:
            if not slot.group_id:
                continue
                
            group = next((g for g in self.groups if g.id == slot.group_id), None)
            if not group:
                continue
                
            group_counts[group.id] = group_counts.get(group.id, 0) + 1
            
            # Check availability
            if not self._is_group_available(group, slot.day, slot.hour):
                errors.append(f"Group {group.name} assigned to unavailable slot Day {slot.day} Hour {slot.hour}")

            # Collect for simultaneous check
            key = (slot.day, slot.hour)
            if key not in slots_by_time:
                slots_by_time[key] = []
            slots_by_time[key].append(group)

        # Check quotas (Scaled if partial week)
        # We need to know if this schedule was generated with a range to validate quotas correctly
        # But validation usually checks absolute numbers.
        # If we want to validate against scaled quotas, we need to recalculate them here.
        # For simplicity, let's skip strict quota validation if it's a partial schedule, 
        # or just warn if it exceeds the FULL week quota (which is always an error).

        for group in self.groups:
            if group.weekly_guard_quota is not None:
                count = group_counts.get(group.id, 0)
                if count > group.weekly_guard_quota:
                     errors.append(f"Group {group.name} exceeded quota: {count} > {group.weekly_guard_quota}")

        # Check simultaneous guarding constraint
        for (day, hour), groups_in_slot in slots_by_time.items():
            if len(groups_in_slot) == 2:
                g1, g2 = groups_in_slot[0], groups_in_slot[1]
                if g1.id == g2.id:
                    if not g1.can_guard_simultaneously:
                        errors.append(f"Group {g1.name} guarding simultaneously at Day {day} Hour {hour} but not allowed")

        return errors
