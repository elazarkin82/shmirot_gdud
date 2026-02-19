from typing import List, Dict, Optional, Tuple
from .models import Group, Schedule, ScheduleSlot, TimeWindow
import random
import math
from datetime import datetime, timedelta

class Scheduler:
    def __init__(self, groups: List[Group]):
        self.groups = groups
        self.schedule: Optional[Schedule] = None

    def fill_schedule(self, schedule: Schedule) -> Schedule:
        self.schedule = schedule
        
        available_groups = [g for g in self.groups if g.validate()]
        if not available_groups:
            return self.schedule

        # Identify empty slots to fill
        empty_slots = [s for s in self.schedule.slots if s.group_id is None]
        filled_slots = [s for s in self.schedule.slots if s.group_id is not None]
        
        if not empty_slots:
            return self.schedule

        total_slots_to_fill = len(empty_slots)
        total_slots_in_range = len(self.schedule.slots)
        
        # Calculate quotas
        # We need to distribute the remaining work among groups based on their definitions
        # taking into account what they already have in filled_slots.
        
        # 1. Calculate current load from pre-filled slots
        current_counts = {g.id: 0 for g in available_groups}
        for s in filled_slots:
            if s.group_id in current_counts:
                current_counts[s.group_id] += 1

        # 2. Calculate target total load for the entire period
        # The period length in weeks
        start_date = datetime.strptime(self.schedule.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(self.schedule.end_date, "%Y-%m-%d")
        days_diff = (end_date - start_date).days + 1
        weeks_ratio = days_diff / 7.0
        
        fixed_quota_groups = [g for g in available_groups if g.weekly_guard_quota is not None]
        proportional_groups = [g for g in available_groups if g.weekly_guard_quota is None and g.staffing_size is not None]
        
        group_targets = {}
        
        # Fixed quotas scaled by time period
        fixed_slots_needed = 0
        for g in fixed_quota_groups:
            target = round(g.weekly_guard_quota * weeks_ratio)
            group_targets[g.id] = target
            fixed_slots_needed += max(0, target - current_counts[g.id]) # Only count what's left to fill
            
        # Remaining slots for proportional groups
        remaining_slots_for_prop = total_slots_to_fill - fixed_slots_needed
        
        total_staffing = sum(g.staffing_size for g in proportional_groups)
        
        if total_staffing > 0:
            for g in proportional_groups:
                # Calculate share of the REMAINING work
                share = (g.staffing_size / total_staffing) * remaining_slots_for_prop
                # Add current count to get total target
                group_targets[g.id] = current_counts[g.id] + round(share)
        
        # Adjust rounding errors to match total slots available
        current_target_sum = sum(group_targets.values())
        # We want the sum of targets to equal total slots in range (filled + empty)
        # But actually we just need to make sure we fill the empty slots.
        # Let's adjust targets so sum(target - current) == len(empty_slots)
        
        needed_sum = sum(max(0, group_targets.get(g.id, 0) - current_counts.get(g.id, 0)) for g in available_groups)
        diff = total_slots_to_fill - needed_sum
        
        if diff != 0:
            # Distribute diff to proportional groups first
            if proportional_groups:
                group_targets[proportional_groups[0].id] += diff
            elif fixed_quota_groups:
                group_targets[fixed_quota_groups[0].id] += diff

        # Sort empty slots by time to fill sequentially (or shuffle for randomness)
        # Shuffling is better to distribute "bad" hours
        random.shuffle(empty_slots)
        
        # Fill slots
        for slot in empty_slots:
            # Try to fill
            # We need to know the other slot in the same hour for simultaneous check
            other_slot = self._get_other_slot(slot)
            other_group_id = other_slot.group_id if other_slot else None
            
            # Select best group
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
                
        # Run improvement
        self.improve_schedule()
        
        return self.schedule

    def improve_schedule(self) -> Schedule:
        if not self.schedule or not self.schedule.slots:
            return self.schedule
            
        iterations = 2000
        
        mutable_slots = [s for s in self.schedule.slots if not s.is_locked]
        if len(mutable_slots) < 2:
            return self.schedule

        current_score = self._calculate_schedule_score()
        
        for _ in range(iterations):
            # Pick two random mutable slots
            s1 = random.choice(mutable_slots)
            s2 = random.choice(mutable_slots)
            
            if s1 == s2: continue
            
            # Try swap
            if self._try_swap(s1, s2, current_score):
                # Swap successful, score updated implicitly (or we could track it)
                pass
                
        return self.schedule

    def _try_swap(self, s1: ScheduleSlot, s2: ScheduleSlot, current_score: float) -> bool:
        g1_id = s1.group_id
        g2_id = s2.group_id
        
        if g1_id == g2_id: return False
        
        g1 = self._get_group(g1_id)
        g2 = self._get_group(g2_id)
        
        # Check validity
        if not self._is_swap_valid(s1, g1, s2, g2):
            return False
            
        # Calculate local score delta
        score_before = self._calculate_local_score(s1, g1) + self._calculate_local_score(s2, g2)
        
        # Swap
        s1.group_id = g2_id
        s2.group_id = g1_id
        
        score_after = self._calculate_local_score(s1, g2) + self._calculate_local_score(s2, g1)
        
        if score_after < score_before:
            return True # Keep swap
        else:
            # Revert
            s1.group_id = g1_id
            s2.group_id = g2_id
            return False

    def _is_swap_valid(self, s1: ScheduleSlot, g1: Optional[Group], s2: ScheduleSlot, g2: Optional[Group]) -> bool:
        # Check availability
        if g1 and not self._is_group_available(g1, s2.day_of_week, s2.hour, s2.date): return False
        if g2 and not self._is_group_available(g2, s1.day_of_week, s1.hour, s1.date): return False
        
        # Check simultaneous
        if g1:
            other_s2 = self._get_other_slot(s2)
            if other_s2 and other_s2.group_id == g1.id and not g1.can_guard_simultaneously: return False
            
        if g2:
            other_s1 = self._get_other_slot(s1)
            if other_s1 and other_s1.group_id == g2.id and not g2.can_guard_simultaneously: return False
            
        return True

    def _get_other_slot(self, slot: ScheduleSlot) -> Optional[ScheduleSlot]:
        other_pos = 2 if slot.position == 1 else 1
        return self.schedule.get_slot(slot.date, slot.hour, other_pos)

    def _get_group(self, group_id: Optional[str]) -> Optional[Group]:
        if not group_id: return None
        return next((g for g in self.groups if g.id == group_id), None)

    def _select_best_group(self, slot: ScheduleSlot, groups: List[Group], current_counts: Dict[str, int], targets: Dict[str, int], other_group_id: Optional[str]) -> Optional[Group]:
        candidates = []
        
        for g in groups:
            # Hard constraint: Availability
            if not self._is_group_available(g, slot.day_of_week, slot.hour, slot.date):
                continue
            
            # Hard constraint: Simultaneous
            if other_group_id == g.id and not g.can_guard_simultaneously:
                continue
                
            score = 0
            
            # Quota progress
            target = targets.get(g.id, 0)
            if target > 0:
                ratio = current_counts[g.id] / target
                if ratio >= 1.0:
                    score += 1000 # Penalty for exceeding
                else:
                    score += ratio * 100
            else:
                score += 2000
                
            # Activity window
            if self._is_activity_window(g, slot.day_of_week, slot.hour):
                score += 500
                
            # Preference for simultaneous if allowed
            if other_group_id == g.id and g.can_guard_simultaneously:
                score -= 50
                
            candidates.append((score, g))
            
        candidates.sort(key=lambda x: x[0])
        
        if candidates:
            return candidates[0][1]
        return None

    def _is_group_available(self, group: Group, day: int, hour: int, date_str: str) -> bool:
        # 1. Check Date Constraints (Specific dates override general rules)
        # Logic:
        # - If there is a "Not Available" constraint for this date/hour -> False
        # - If there is an "Available" constraint for this date -> Only True if within that constraint's hours
        
        has_positive_constraint_for_date = False
        is_allowed_by_positive = False
        
        for constraint in group.date_constraints:
            if date_str in constraint.dates:
                if not constraint.is_available:
                    # Negative constraint: If we are in the forbidden range, return False
                    if constraint.start_hour <= hour < constraint.end_hour:
                        return False
                else:
                    # Positive constraint: We found at least one rule saying "Available here"
                    has_positive_constraint_for_date = True
                    if constraint.start_hour <= hour < constraint.end_hour:
                        is_allowed_by_positive = True
        
        if has_positive_constraint_for_date:
            # If we have positive constraints for this day, we must satisfy at least one of them
            if not is_allowed_by_positive:
                return False
            # If satisfied, we ignore general weekly rules? 
            # Usually specific overrides general. So if I say "Available 8-12 on 1/1", 
            # I probably don't care about "Not available on Sundays".
            return True

        # 2. Check General Weekly Constraints
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

    def _calculate_schedule_score(self) -> float:
        score = 0
        for slot in self.schedule.slots:
            group = self._get_group(slot.group_id)
            score += self._calculate_local_score(slot, group)
        return score

    def _calculate_local_score(self, slot: ScheduleSlot, group: Optional[Group]) -> float:
        if not group: return 0
        score = 0
        
        if self._is_activity_window(group, slot.day_of_week, slot.hour):
            score += 100
            
        other = self._get_other_slot(slot)
        if other and other.group_id == group.id:
            score -= 50
            
        return score

    def validate_schedule(self) -> List[str]:
        errors = []
        # Basic validation
        for slot in self.schedule.slots:
            if slot.group_id:
                group = self._get_group(slot.group_id)
                if not group: continue
                
                if not self._is_group_available(group, slot.day_of_week, slot.hour, slot.date):
                    errors.append(f"Group {group.name} unavailable at {slot.date} {slot.hour}:00")
                    
                other = self._get_other_slot(slot)
                if other and other.group_id == group.id and not group.can_guard_simultaneously:
                    errors.append(f"Group {group.name} double guarding at {slot.date} {slot.hour}:00")

        return errors
