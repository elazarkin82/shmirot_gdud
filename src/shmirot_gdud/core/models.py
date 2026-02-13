from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum
import json
import random

class ConstraintType(Enum):
    UNAVAILABILITY = "unavailability"
    ACTIVITY_WINDOW = "activity_window"

def generate_pastel_color():
    """Generates a random pastel color for better text visibility."""
    r = random.randint(180, 255)
    g = random.randint(180, 255)
    b = random.randint(180, 255)
    return f"#{r:02x}{g:02x}{b:02x}"

@dataclass
class TimeWindow:
    day: int  # 0-6
    start_hour: int # 0-23
    end_hour: int # 0-23

    def to_dict(self):
        return {
            "day": self.day,
            "start_hour": self.start_hour,
            "end_hour": self.end_hour
        }

    @staticmethod
    def from_dict(data):
        return TimeWindow(
            day=data["day"],
            start_hour=data["start_hour"],
            end_hour=data["end_hour"]
        )

@dataclass
class Group:
    id: str
    name: str
    staffing_size: Optional[int] = None
    weekly_guard_quota: Optional[int] = None # Hard constraint if set
    hard_unavailability_rules: List[TimeWindow] = field(default_factory=list)
    primary_activity_windows: List[TimeWindow] = field(default_factory=list)
    can_guard_simultaneously: bool = True
    color: str = field(default_factory=generate_pastel_color)
    
    def validate(self) -> bool:
        return self.staffing_size is not None or self.weekly_guard_quota is not None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "staffing_size": self.staffing_size,
            "weekly_guard_quota": self.weekly_guard_quota,
            "hard_unavailability_rules": [r.to_dict() for r in self.hard_unavailability_rules],
            "primary_activity_windows": [w.to_dict() for w in self.primary_activity_windows],
            "can_guard_simultaneously": self.can_guard_simultaneously,
            "color": self.color
        }

    @staticmethod
    def from_dict(data):
        return Group(
            id=data["id"],
            name=data["name"],
            staffing_size=data.get("staffing_size"),
            weekly_guard_quota=data.get("weekly_guard_quota"),
            hard_unavailability_rules=[TimeWindow.from_dict(r) for r in data.get("hard_unavailability_rules", [])],
            primary_activity_windows=[TimeWindow.from_dict(w) for w in data.get("primary_activity_windows", [])],
            can_guard_simultaneously=data.get("can_guard_simultaneously", True),
            color=data.get("color", generate_pastel_color())
        )

@dataclass
class ScheduleSlot:
    day: int
    hour: int
    position: int # 1 or 2
    group_id: Optional[str] = None

@dataclass
class WeeklySchedule:
    week_start_date: str # ISO format YYYY-MM-DD
    slots: List[ScheduleSlot] = field(default_factory=list)

    def get_slot(self, day: int, hour: int, position: int) -> Optional[ScheduleSlot]:
        for slot in self.slots:
            if slot.day == day and slot.hour == hour and slot.position == position:
                return slot
        return None

    def set_slot(self, day: int, hour: int, position: int, group_id: str):
        slot = self.get_slot(day, hour, position)
        if slot:
            slot.group_id = group_id
        else:
            self.slots.append(ScheduleSlot(day, hour, position, group_id))
