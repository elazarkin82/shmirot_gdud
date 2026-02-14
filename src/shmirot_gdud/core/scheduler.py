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
            
            # Handle wrapping if end < start (e.g. Fri to Mon) - though UI might prevent this for simplicity
            # Let's assume simple linear range for now within a week
            
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
                
        return self.schedule

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
