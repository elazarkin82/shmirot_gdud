from dataclasses import dataclass
from typing import List, Optional

@dataclass
class TimeWindow:
    day: int
    start_hour: int
    end_hour: int

    def to_dict(self):
        return {"day": self.day, "start_hour": self.start_hour, "end_hour": self.end_hour}

    @staticmethod
    def from_dict(data):
        return TimeWindow(data["day"], data["start_hour"], data["end_hour"])

@dataclass
class StaffingRule:
    day: int
    start_hour: int
    end_hour: int
    max_capacity: Optional[int] = None
    force_coupling: bool = False
    uid: str = ""

    def to_dict(self):
        return {
            "day": self.day,
            "start_hour": self.start_hour,
            "end_hour": self.end_hour,
            "max_capacity": self.max_capacity,
            "force_coupling": self.force_coupling,
            "uid": self.uid
        }

    @staticmethod
    def from_dict(data):
        rule = StaffingRule(
            data["day"], data["start_hour"], data["end_hour"],
            data.get("max_capacity"), data.get("force_coupling", False)
        )
        if "uid" in data: rule.uid = data["uid"]
        return rule

@dataclass
class StaffingException:
    start_date: str
    start_hour: int
    end_date: str
    end_hour: int
    new_staffing_size: int

    def to_dict(self):
        return {
            "start_date": self.start_date,
            "start_hour": self.start_hour,
            "end_date": self.end_date,
            "end_hour": self.end_hour,
            "new_staffing_size": self.new_staffing_size
        }

    @staticmethod
    def from_dict(data):
        return StaffingException(
            data["start_date"], data["start_hour"],
            data["end_date"], data["end_hour"],
            data["new_staffing_size"]
        )

@dataclass
class DateConstraint:
    dates: List[str]
    start_hour: int
    end_hour: int
    is_available: bool

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
            data["dates"], data["start_hour"], data["end_hour"], data["is_available"]
        )

@dataclass
class ScheduleRange:
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
