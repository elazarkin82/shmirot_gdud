from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
import random
from shmirot_gdud.core.base.constraint import ConstraintBase
from shmirot_gdud.core.base.context import ScheduleContext
from shmirot_gdud.core.basic_models import TimeWindow, StaffingRule, StaffingException, DateConstraint, ScheduleRange
from shmirot_gdud.core.config import config
from datetime import datetime, timedelta

def generate_pastel_color():
    r = random.randint(180, 255)
    g = random.randint(180, 255)
    b = random.randint(180, 255)
    return f"#{r:02x}{g:02x}{b:02x}"

@dataclass
class Group:
    id: str
    name: str
    staffing_size: Optional[int] = None
    weekly_guard_quota: Optional[int] = None
    staffing_exceptions: List[StaffingException] = field(default_factory=list)
    constraints: List[ConstraintBase] = field(default_factory=list)
    can_guard_simultaneously: bool = True 
    color: str = field(default_factory=generate_pastel_color)
    
    # Caching fields
    _cached_score: Optional[float] = field(default=None, init=False)
    _is_dirty: bool = field(default=True, init=False)
    _assigned_slots: Set['ScheduleSlot'] = field(default_factory=set, init=False)
    
    def __post_init__(self):
        # Ensure default constraints exist
        from shmirot_gdud.core.constraints.implementations import SimultaneousConstraint, ConsecutiveConstraint, RestConstraint
        
        # Simultaneous
        sim_constraint = next((c for c in self.constraints if isinstance(c, SimultaneousConstraint)), None)
        if not sim_constraint:
            self.constraints.append(SimultaneousConstraint(self.can_guard_simultaneously))
        else:
            sim_constraint.allowed = self.can_guard_simultaneously # Sync
            
        # Consecutive
        if not any(isinstance(c, ConsecutiveConstraint) for c in self.constraints):
            self.constraints.append(ConsecutiveConstraint())
            
        # Rest
        if not any(isinstance(c, RestConstraint) for c in self.constraints):
            self.constraints.append(RestConstraint())

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, Group): return False
        return self.id == other.id

    def validate(self) -> bool:
        return self.staffing_size is not None or self.weekly_guard_quota is not None

    def invalidate_cache(self):
        self._is_dirty = True
        self._cached_score = None

    def get_score(self, context: ScheduleContext) -> float:
        if not self._is_dirty and self._cached_score is not None:
            return self._cached_score
        
        self._cached_score = self._calculate_total_score(context)
        self._is_dirty = False
        return self._cached_score

    def _calculate_total_score(self, context: ScheduleContext) -> float:
        score = 0.0
        from shmirot_gdud.core.constraints.implementations import ConsecutiveConstraint, RestConstraint
        
        # 1. Local Constraints Score
        for slot in self._assigned_slots:
            for constraint in self.constraints:
                # Skip global constraints here, they are handled below
                if isinstance(constraint, (ConsecutiveConstraint, RestConstraint)): continue
                
                s = constraint.calculate_score(slot, context)
                if s is not None:
                    score += s
                else:
                    score -= 100000

        # 2. Global Constraints Score
        for constraint in self.constraints:
            if isinstance(constraint, ConsecutiveConstraint):
                score += constraint.calculate_global_score(list(self._assigned_slots), self.staffing_size, self.staffing_exceptions)
            elif isinstance(constraint, RestConstraint):
                score += constraint.calculate_global_score(list(self._assigned_slots))
        
        return score

    def calculate_score(self, slot: 'ScheduleSlot', context: ScheduleContext) -> Optional[float]:
        # Calculates score for a SINGLE potential assignment (used in fill_schedule / delta)
        total_score = 0.0
        context.group_id = self.id 
        
        from shmirot_gdud.core.constraints.implementations import ConsecutiveConstraint, RestConstraint

        for constraint in self.constraints:
            # Skip global constraints for local delta estimation if they return 0
            if isinstance(constraint, (ConsecutiveConstraint, RestConstraint)): continue

            score = constraint.calculate_score(slot, context)
            if score is None:
                return None 
            total_score += score
        return total_score

    def is_available(self, slot: 'ScheduleSlot', context: ScheduleContext) -> bool:
        context.group_id = self.id
        for constraint in self.constraints:
            if constraint.is_hard_constraint():
                if not constraint.validate(slot, context):
                    return False
        return True

    def notify_assignment(self, slot: 'ScheduleSlot', context: ScheduleContext):
        self._assigned_slots.add(slot)
        self.invalidate_cache()
        
        context.group_id = self.id
        for constraint in self.constraints:
            constraint.on_assign(slot, context)

    def notify_removal(self, slot: 'ScheduleSlot', context: ScheduleContext):
        if slot in self._assigned_slots:
            self._assigned_slots.remove(slot)
            self.invalidate_cache()
            
        context.group_id = self.id
        for constraint in self.constraints:
            constraint.on_remove(slot, context)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "staffing_size": self.staffing_size,
            "weekly_guard_quota": self.weekly_guard_quota,
            "staffing_exceptions": [e.to_dict() for e in self.staffing_exceptions],
            "constraints": [c.to_dict() for c in self.constraints],
            "can_guard_simultaneously": self.can_guard_simultaneously,
            "color": self.color
        }

    @staticmethod
    def from_dict(data):
        from shmirot_gdud.core.constraints.factory import ConstraintFactory
        
        constraints = []
        if "constraints" in data:
            for c_data in data["constraints"]:
                try:
                    constraints.append(ConstraintFactory.create_from_dict(c_data))
                except ValueError:
                    pass 
        else:
            # Migration logic
            if "hard_unavailability_rules" in data and data["hard_unavailability_rules"]:
                constraints.append(ConstraintFactory.create_from_dict({
                    "type": "unavailability",
                    "rules": [r for r in data["hard_unavailability_rules"]]
                }))
            if "primary_activity_windows" in data and data["primary_activity_windows"]:
                constraints.append(ConstraintFactory.create_from_dict({
                    "type": "activity_window",
                    "windows": [w for w in data["primary_activity_windows"]]
                }))
            if "date_constraints" in data and data["date_constraints"]:
                constraints.append(ConstraintFactory.create_from_dict({
                    "type": "date_specific",
                    "constraints": [c for c in data["date_constraints"]]
                }))
            if "staffing_rules" in data and data["staffing_rules"]:
                constraints.append(ConstraintFactory.create_from_dict({
                    "type": "staffing_rules",
                    "rules": [r for r in data["staffing_rules"]]
                }))

        return Group(
            id=data["id"],
            name=data["name"],
            staffing_size=data.get("staffing_size"),
            weekly_guard_quota=data.get("weekly_guard_quota"),
            staffing_exceptions=[StaffingException.from_dict(e) for e in data.get("staffing_exceptions", [])],
            constraints=constraints,
            can_guard_simultaneously=data.get("can_guard_simultaneously", True),
            color=data.get("color", generate_pastel_color())
        )

@dataclass
class ScheduleSlot:
    date: str
    day_of_week: int
    hour: int
    position: int
    group_id: Optional[str] = None
    is_locked: bool = False

    def __hash__(self):
        return hash((self.date, self.hour, self.position))

    def __eq__(self, other):
        if not isinstance(other, ScheduleSlot): return False
        return (self.date, self.hour, self.position) == (other.date, other.hour, other.position)

    def to_dict(self):
        return {
            "date": self.date,
            "day_of_week": self.day_of_week,
            "hour": self.hour,
            "position": self.position,
            "group_id": self.group_id,
            "is_locked": self.is_locked
        }

    @staticmethod
    def from_dict(data):
        return ScheduleSlot(
            date=data.get("date", ""),
            day_of_week=data.get("day_of_week", data.get("day", 0)),
            hour=data["hour"],
            position=data["position"],
            group_id=data.get("group_id"),
            is_locked=data.get("is_locked", False)
        )

@dataclass
class Schedule:
    start_date: str
    end_date: str
    slots: List[ScheduleSlot] = field(default_factory=list)

    @staticmethod
    def create_empty(start_date_str: str, end_date_str: str) -> 'Schedule':
        start = datetime.strptime(start_date_str, "%Y-%m-%d")
        end = datetime.strptime(end_date_str, "%Y-%m-%d")
        slots = []
        current = start
        while current <= end:
            py_weekday = current.weekday()
            our_weekday = (py_weekday + 1) % 7
            date_str = current.strftime("%Y-%m-%d")
            for hour in range(24):
                slots.append(ScheduleSlot(date_str, our_weekday, hour, 1))
                slots.append(ScheduleSlot(date_str, our_weekday, hour, 2))
            current += timedelta(days=1)
        return Schedule(start_date_str, end_date_str, slots)

    def get_slot(self, date: str, hour: int, position: int) -> Optional[ScheduleSlot]:
        for slot in self.slots:
            if slot.date == date and slot.hour == hour and slot.position == position:
                return slot
        return None

    def set_slot(self, date: str, hour: int, position: int, group_id: str, lock: bool = False):
        slot = self.get_slot(date, hour, position)
        if slot:
            slot.group_id = group_id
            slot.is_locked = lock

    def to_dict(self):
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "slots": [s.to_dict() for s in self.slots]
        }

    @staticmethod
    def from_dict(data):
        if "week_start_date" in data and "start_date" not in data:
            start = data["week_start_date"]
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = start_dt + timedelta(days=6)
            end = end_dt.strftime("%Y-%m-%d")
            slots = []
            for s_data in data.get("slots", []):
                day_idx = s_data.get("day", 0)
                slot_date = (start_dt + timedelta(days=day_idx)).strftime("%Y-%m-%d")
                s_data["date"] = slot_date
                s_data["day_of_week"] = day_idx
                slots.append(ScheduleSlot.from_dict(s_data))
            return Schedule(start, end, slots)

        return Schedule(
            start_date=data["start_date"],
            end_date=data["end_date"],
            slots=[ScheduleSlot.from_dict(s) for s in data.get("slots", [])]
        )
