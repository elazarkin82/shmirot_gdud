from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum
import json
import random
from datetime import datetime, timedelta

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
    day: int  # 0-6 (Sunday-Saturday)
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
class DateConstraint:
    dates: List[str] # List of ISO date strings "YYYY-MM-DD"
    start_hour: int
    end_hour: int
    is_available: bool # True = Available only at these times, False = Not available

    def to_dict(self):
        return {
            "dates": self.dates,
            "start_hour": self.start_hour,
            "end_hour": self.end_hour,
            "is_available": self.is_available
        }

    @staticmethod
    def from_dict(data):
        return DateConstraint(
            dates=data["dates"],
            start_hour=data["start_hour"],
            end_hour=data["end_hour"],
            is_available=data["is_available"]
        )

@dataclass
class Group:
    id: str
    name: str
    staffing_size: Optional[int] = None
    weekly_guard_quota: Optional[int] = None # Hard constraint if set
    hard_unavailability_rules: List[TimeWindow] = field(default_factory=list)
    primary_activity_windows: List[TimeWindow] = field(default_factory=list)
    date_constraints: List[DateConstraint] = field(default_factory=list) # New field
    can_guard_simultaneously: bool = True
    color: str = field(default_factory=generate_pastel_color)
    
    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, Group):
            return False
        return self.id == other.id

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
            "date_constraints": [c.to_dict() for c in self.date_constraints],
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
            date_constraints=[DateConstraint.from_dict(c) for c in data.get("date_constraints", [])],
            can_guard_simultaneously=data.get("can_guard_simultaneously", True),
            color=data.get("color", generate_pastel_color())
        )

@dataclass
class ScheduleSlot:
    date: str # ISO format YYYY-MM-DD
    day_of_week: int # 0-6 (Sunday=0)
    hour: int
    position: int # 1 or 2
    group_id: Optional[str] = None
    is_locked: bool = False # If True, optimization won't touch this slot

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
            day_of_week=data.get("day_of_week", data.get("day", 0)), # Fallback for old format
            hour=data["hour"],
            position=data["position"],
            group_id=data.get("group_id"),
            is_locked=data.get("is_locked", False)
        )

@dataclass
class ScheduleRange:
    # Kept for backward compatibility or specific partial generation logic if needed
    start_day: int
    start_hour: int
    end_day: int
    end_hour: int

    def to_dict(self):
        return {
            "start_day": self.start_day,
            "start_hour": self.start_hour,
            "end_day": self.end_day,
            "end_hour": self.end_hour
        }

    @staticmethod
    def from_dict(data):
        return ScheduleRange(
            start_day=data["start_day"],
            start_hour=data["start_hour"],
            end_day=data["end_day"],
            end_hour=data["end_hour"]
        )

@dataclass
class Schedule:
    start_date: str # ISO format YYYY-MM-DD
    end_date: str # ISO format YYYY-MM-DD
    slots: List[ScheduleSlot] = field(default_factory=list)

    @staticmethod
    def create_empty(start_date_str: str, end_date_str: str) -> 'Schedule':
        start = datetime.strptime(start_date_str, "%Y-%m-%d")
        end = datetime.strptime(end_date_str, "%Y-%m-%d")
        
        slots = []
        current = start
        while current <= end:
            # In Python weekday() is Mon=0, Sun=6. 
            # We want Sun=0, Sat=6.
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
        # Handle migration from old WeeklySchedule if needed
        if "week_start_date" in data and "start_date" not in data:
            # Convert old format to new format roughly
            start = data["week_start_date"]
            # Assume 7 days for old format
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = start_dt + timedelta(days=6)
            end = end_dt.strftime("%Y-%m-%d")
            
            slots = []
            for s_data in data.get("slots", []):
                # Convert day index to date
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
