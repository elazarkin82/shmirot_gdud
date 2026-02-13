from typing import List, Dict, Optional, Tuple
from .models import Group, WeeklySchedule, ScheduleSlot, TimeWindow
import random
import math

class Scheduler:
    def __init__(self, groups: List[Group]):
        self.groups = groups
        self.schedule = WeeklySchedule(week_start_date="2023-01-01") # Placeholder date

    def generate_schedule(self) -> WeeklySchedule:
        # Initialize empty schedule
        self.schedule.slots = []
        
        available_groups = [g for g in self.groups if g.validate()]
        if not available_groups:
            return self.schedule

        # Calculate target quotas
        total_slots = 7 * 24 * 2
        fixed_quota_groups = [g for g in available_groups if g.weekly_guard_quota is not None]
        proportional_groups = [g for g in available_groups if g.weekly_guard_quota is None and g.staffing_size is not None]
        
        fixed_slots_needed = sum(g.weekly_guard_quota for g in fixed_quota_groups)
        remaining_slots = total_slots - fixed_slots_needed
        
        total_staffing = sum(g.staffing_size for g in proportional_groups)
        
        group_targets = {}
        for g in fixed_quota_groups:
            group_targets[g.id] = g.weekly_guard_quota
            
        if total_staffing > 0:
            for g in proportional_groups:
                share = (g.staffing_size / total_staffing) * remaining_slots
                group_targets[g.id] = round(share)
        
        # Adjust rounding errors
        current_total = sum(group_targets.values())
        diff = total_slots - current_total
        if diff != 0 and proportional_groups:
             group_targets[proportional_groups[0].id] += diff

        # Create time slots (day, hour) to fill
        time_slots = []
        for day in range(7):
            for hour in range(24):
                time_slots.append((day, hour))
        
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
        
        for slot in self.schedule.slots:
            if not slot.group_id:
                continue
                
            group = next((g for g in self.groups if g.id == slot.group_id), None)
            if not group:
                continue
                
            group_counts[group.id] = group_counts.get(group.id, 0) + 1
            
            if not self._is_group_available(group, slot.day, slot.hour):
                errors.append(f"Group {group.name} assigned to unavailable slot Day {slot.day} Hour {slot.hour}")

        for group in self.groups:
            if group.weekly_guard_quota is not None:
                count = group_counts.get(group.id, 0)
                if count > group.weekly_guard_quota:
                     errors.append(f"Group {group.name} exceeded quota: {count} > {group.weekly_guard_quota}")
        
        return errors
