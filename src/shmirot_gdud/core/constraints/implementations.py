from typing import List, Dict, Any, Callable, Optional
from shmirot_gdud.core.base.constraint import ConstraintBase
from shmirot_gdud.core.base.context import ScheduleContext
from shmirot_gdud.core.config import config
import uuid
from datetime import datetime

class UnavailabilityConstraint(ConstraintBase):
    def __init__(self, rules: List[Dict[str, int]] = None):
        super().__init__()
        self.rules = rules if rules else []

    def get_type_id(self) -> str:
        return "unavailability"

    def get_display_name(self) -> str:
        return "ניהול אי-זמינות"

    def get_status_text(self) -> str:
        return f"{len(self.rules)} חוקים"

    def open_edit_dialog(self, parent, on_save: Callable[['ConstraintBase'], None]):
        from shmirot_gdud.gui.dialogs import TimeWindowDialog
        from shmirot_gdud.core.models import TimeWindow
        windows = [TimeWindow.from_dict(r) for r in self.rules]
        def save_callback(new_windows: List[TimeWindow]):
            self.rules = [w.to_dict() for w in new_windows]
            on_save(self)
        TimeWindowDialog(parent, "ניהול אי-זמינות", windows, save_callback)

    def check_validity(self, slot, context: ScheduleContext) -> bool:
        for r in self.rules:
            if r['day'] == slot.day_of_week:
                if r['start_hour'] <= slot.hour < r['end_hour']:
                    return False
        return True

    def calculate_score(self, slot, context: ScheduleContext) -> float:
        return 0.0

    def is_hard_constraint(self) -> bool:
        return True

    def validate(self, slot, context) -> bool:
        return self.check_validity(slot, context)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.get_type_id(), "rules": self.rules, "uid": self.uid}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UnavailabilityConstraint':
        c = cls(data.get("rules", []))
        if "uid" in data: c.uid = data["uid"]
        return c


class ActivityWindowConstraint(ConstraintBase):
    def __init__(self, windows: List[Dict[str, int]] = None):
        super().__init__()
        self.windows = windows if windows else []

    def get_type_id(self) -> str:
        return "activity_window"

    def get_display_name(self) -> str:
        return "חלונות פעילות"

    def get_status_text(self) -> str:
        return f"{len(self.windows)} חלונות"

    def open_edit_dialog(self, parent, on_save: Callable[['ConstraintBase'], None]):
        from shmirot_gdud.gui.dialogs import TimeWindowDialog
        from shmirot_gdud.core.models import TimeWindow
        windows_objs = [TimeWindow.from_dict(w) for w in self.windows]
        def save_callback(new_windows: List[TimeWindow]):
            self.windows = [w.to_dict() for w in new_windows]
            on_save(self)
        TimeWindowDialog(parent, "ניהול חלונות פעילות", windows_objs, save_callback)

    def check_validity(self, slot, context: ScheduleContext) -> bool:
        return True

    def calculate_score(self, slot, context: ScheduleContext) -> float:
        for w in self.windows:
            if w['day'] == slot.day_of_week:
                if w['start_hour'] <= slot.hour < w['end_hour']:
                    return -config.ACTIVITY_WINDOW_PENALTY
        return 0.0

    def is_hard_constraint(self) -> bool:
        return False

    def validate(self, slot, context) -> bool:
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.get_type_id(), "windows": self.windows, "uid": self.uid}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ActivityWindowConstraint':
        c = cls(data.get("windows", []))
        if "uid" in data: c.uid = data["uid"]
        return c


class DateSpecificConstraint(ConstraintBase):
    def __init__(self, constraints: List[Dict[str, Any]] = None):
        super().__init__()
        self.constraints = constraints if constraints else []

    def get_type_id(self) -> str:
        return "date_specific"

    def get_display_name(self) -> str:
        return "אילוצי תאריכים"

    def get_status_text(self) -> str:
        return f"{len(self.constraints)} אילוצים"

    def open_edit_dialog(self, parent, on_save: Callable[['ConstraintBase'], None]):
        from shmirot_gdud.gui.dialogs import DateConstraintDialog
        from shmirot_gdud.core.models import DateConstraint
        objs = [DateConstraint.from_dict(c) for c in self.constraints]
        def save_callback(new_objs: List[DateConstraint]):
            self.constraints = [c.to_dict() for c in new_objs]
            on_save(self)
        DateConstraintDialog(parent, "אילוצי תאריכים", objs, save_callback)

    def check_validity(self, slot, context: ScheduleContext) -> bool:
        date_str = slot.date
        has_positive = False
        allowed = False
        
        for c in self.constraints:
            if date_str in c['dates']:
                if not c['is_available']:
                    if c['start_hour'] <= slot.hour < c['end_hour']:
                        return False
                else:
                    has_positive = True
                    if c['start_hour'] <= slot.hour < c['end_hour']:
                        allowed = True
        
        if has_positive:
            return allowed
        return True

    def calculate_score(self, slot, context: ScheduleContext) -> float:
        return 0.0

    def is_hard_constraint(self) -> bool:
        return True

    def validate(self, slot, context) -> bool:
        return self.check_validity(slot, context)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.get_type_id(), "constraints": self.constraints, "uid": self.uid}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DateSpecificConstraint':
        c = cls(data.get("constraints", []))
        if "uid" in data: c.uid = data["uid"]
        return c


class StaffingRuleConstraint(ConstraintBase):
    def __init__(self, rules: List[Dict[str, Any]] = None):
        super().__init__()
        self.rules = rules if rules else []
        for r in self.rules:
            if 'uid' not in r:
                r['uid'] = str(uuid.uuid4())

    def get_type_id(self) -> str:
        return "staffing_rules"

    def get_display_name(self) -> str:
        return "חוקי איוש (זוגות/כמות)"

    def get_status_text(self) -> str:
        return f"{len(self.rules)} חוקים"

    def open_edit_dialog(self, parent, on_save: Callable[['ConstraintBase'], None]):
        from shmirot_gdud.gui.dialogs import StaffingRulesDialog
        from shmirot_gdud.core.models import StaffingRule
        objs = [StaffingRule.from_dict(r) for r in self.rules]
        def save_callback(new_objs: List[StaffingRule]):
            self.rules = [r.to_dict() for r in new_objs]
            for r in self.rules:
                if 'uid' not in r: r['uid'] = str(uuid.uuid4())
            on_save(self)
        StaffingRulesDialog(parent, "חוקי איוש", objs, save_callback)

    def check_validity(self, slot, context: ScheduleContext) -> bool:
        group_id = context.group_id if hasattr(context, 'group_id') else None
        if not group_id: return True
        
        other_group_id = getattr(context, 'other_group_id', None)
        
        for r in self.rules:
            if r['day'] == slot.day_of_week and r['start_hour'] <= slot.hour < r['end_hour']:
                
                if r.get('max_capacity') is not None:
                    current_usage = context.get_usage(r['uid'])
                    increment = 1
                    if getattr(context, 'is_initial_fill', False) and r.get('force_coupling') and other_group_id is None:
                        increment = 2
                    if current_usage + increment > r['max_capacity']:
                        return False

                if r.get('force_coupling'):
                    if other_group_id is not None and other_group_id != group_id:
                        return False
                        
        return True

    def calculate_score(self, slot, context: ScheduleContext) -> float:
        score = 0.0
        for r in self.rules:
            if r['day'] == slot.day_of_week and r['start_hour'] <= slot.hour < r['end_hour']:
                if r.get('force_coupling'):
                    score += config.STAFFING_RULE_BONUS
        return score

    def on_assign(self, slot, context: ScheduleContext):
        for r in self.rules:
            if r['day'] == slot.day_of_week and r['start_hour'] <= slot.hour < r['end_hour']:
                context.update_usage(r['uid'], 1)

    def on_remove(self, slot, context: ScheduleContext):
        for r in self.rules:
            if r['day'] == slot.day_of_week and r['start_hour'] <= slot.hour < r['end_hour']:
                context.update_usage(r['uid'], -1)

    def is_hard_constraint(self) -> bool:
        return True

    def validate(self, slot, context) -> bool:
        return self.check_validity(slot, context)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.get_type_id(), "rules": self.rules, "uid": self.uid}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StaffingRuleConstraint':
        c = cls(data.get("rules", []))
        if "uid" in data: c.uid = data["uid"]
        for r in c.rules:
            if 'uid' not in r: r['uid'] = str(uuid.uuid4())
        return c


class SimultaneousConstraint(ConstraintBase):
    def __init__(self, allowed: bool = True):
        super().__init__()
        self.allowed = allowed

    def get_type_id(self) -> str:
        return "simultaneous"

    def get_display_name(self) -> str:
        return "שמירה כפולה"

    def get_status_text(self) -> str:
        return "מותר" if self.allowed else "אסור"

    def open_edit_dialog(self, parent, on_save: Callable[['ConstraintBase'], None]):
        pass # Managed by checkbox in main dialog

    def check_validity(self, slot, context: ScheduleContext) -> bool:
        if self.allowed: return True
        
        # If not allowed, check if other slot has same group
        other = context.get_other_slot(slot)
        # In improve_schedule, we pass 'other_group_id' in context
        other_gid = getattr(context, 'other_group_id', None)
        
        if other_gid is None and other:
            other_gid = other.group_id
            
        my_gid = getattr(context, 'group_id', None)
        
        if other_gid and my_gid and other_gid == my_gid:
            return False
            
        return True

    def calculate_score(self, slot, context: ScheduleContext) -> float:
        # Bonus for simultaneous if allowed
        if not self.allowed: return 0.0
        
        other = context.get_other_slot(slot)
        other_gid = getattr(context, 'other_group_id', None)
        if other_gid is None and other:
            other_gid = other.group_id
            
        my_gid = getattr(context, 'group_id', None)
        
        if other_gid and my_gid and other_gid == my_gid:
            return config.SIMULTANEOUS_BONUS
            
        return 0.0

    def is_hard_constraint(self) -> bool:
        return True

    def validate(self, slot, context) -> bool:
        return self.check_validity(slot, context)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.get_type_id(), "allowed": self.allowed}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SimultaneousConstraint':
        return cls(data.get("allowed", True))


class ConsecutiveConstraint(ConstraintBase):
    def __init__(self):
        super().__init__()

    def get_type_id(self) -> str:
        return "consecutive"

    def get_display_name(self) -> str:
        return "רצף משמרות"

    def get_status_text(self) -> str:
        return "פעיל"

    def open_edit_dialog(self, parent, on_save: Callable[['ConstraintBase'], None]):
        pass

    def check_validity(self, slot, context: ScheduleContext) -> bool:
        return True

    def calculate_score(self, slot, context: ScheduleContext) -> float:
        # This is tricky because it depends on the sequence.
        # We need to know the sequence length INCLUDING this slot.
        # But context doesn't easily provide "what if" sequence.
        # However, Group.calculate_score calls this.
        # Group has _assigned_slots.
        # If we are in calculate_score, the slot is NOT yet in _assigned_slots (usually).
        # But Group._calculate_total_score iterates over _assigned_slots.
        
        # So this constraint is used for GLOBAL score calculation of the group.
        # It is NOT used for local delta of a single slot easily.
        
        # We return 0 here because the logic is complex and handled by Group._calculate_sequence_score
        # which we will move here or keep in Group.
        # To be fully modular, we should move it here.
        return 0.0

    def calculate_global_score(self, group_slots: List, staffing_size: int, staffing_exceptions: List) -> float:
        # Logic moved from Group._calculate_sequence_score
        score = 0.0
        if not group_slots: return 0.0
        
        sorted_slots = sorted(list(group_slots), key=lambda s: (s.date, s.hour))
        active_hours = sorted(list(set((s.date, s.hour) for s in sorted_slots)))
        
        current_seq = 0
        
        for i, (date_str, hour) in enumerate(active_hours):
            dt = datetime.strptime(f"{date_str} {hour}:00", "%Y-%m-%d %H:%M")
            
            if i > 0:
                prev_date, prev_hour = active_hours[i-1]
                prev_dt = datetime.strptime(f"{prev_date} {prev_hour}:00", "%Y-%m-%d %H:%M")
                gap_hours = (dt - prev_dt).total_seconds() / 3600
                
                if gap_hours == 1.0:
                    current_seq += 1
                else:
                    score += self._evaluate_sequence(current_seq, prev_date, prev_hour, staffing_size, staffing_exceptions)
                    current_seq = 1
            else:
                current_seq = 1
                
        if active_hours:
            last_date, last_hour = active_hours[-1]
            score += self._evaluate_sequence(current_seq, last_date, last_hour, staffing_size, staffing_exceptions)
            
        return score

    def _evaluate_sequence(self, length: int, date_str: str, hour: int, staffing_size: int, exceptions: List) -> float:
        staffing = staffing_size if staffing_size else 4
        for exc in exceptions:
             try:
                dt = datetime.strptime(f"{date_str} {hour}:00", "%Y-%m-%d %H:%M")
                start_dt = datetime.strptime(f"{exc.start_date} {exc.start_hour}:00", "%Y-%m-%d %H:%M")
                end_dt = datetime.strptime(f"{exc.end_date} {exc.end_hour}:00", "%Y-%m-%d %H:%M")
                if start_dt <= dt < end_dt:
                    staffing = exc.new_staffing_size
                    break
             except: pass
             
        max_consecutive = staffing // 2
        if max_consecutive < 2: max_consecutive = 2
        if staffing == 2: max_consecutive = 2
        
        score = 0
        if length <= max_consecutive:
            score += length * config.CONSECUTIVE_BONUS_PER_HOUR
        else:
            excess = length - max_consecutive
            score -= (excess ** config.CONSECUTIVE_PENALTY_EXPONENT) * config.CONSECUTIVE_PENALTY_MULTIPLIER
        return score

    def is_hard_constraint(self) -> bool:
        return False

    def validate(self, slot, context) -> bool:
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.get_type_id()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConsecutiveConstraint':
        return cls()


class RestConstraint(ConstraintBase):
    def __init__(self):
        super().__init__()

    def get_type_id(self) -> str:
        return "rest"

    def get_display_name(self) -> str:
        return "מנוחה"

    def get_status_text(self) -> str:
        return "פעיל"

    def open_edit_dialog(self, parent, on_save: Callable[['ConstraintBase'], None]):
        pass

    def check_validity(self, slot, context: ScheduleContext) -> bool:
        return True

    def calculate_score(self, slot, context: ScheduleContext) -> float:
        return 0.0

    def calculate_global_score(self, group_slots: List) -> float:
        score = 0.0
        if not group_slots: return 0.0
        
        sorted_slots = sorted(list(group_slots), key=lambda s: (s.date, s.hour))
        active_hours = sorted(list(set((s.date, s.hour) for s in sorted_slots)))
        
        for i, (date_str, hour) in enumerate(active_hours):
            if i > 0:
                dt = datetime.strptime(f"{date_str} {hour}:00", "%Y-%m-%d %H:%M")
                prev_date, prev_hour = active_hours[i-1]
                prev_dt = datetime.strptime(f"{prev_date} {prev_hour}:00", "%Y-%m-%d %H:%M")
                gap_hours = (dt - prev_dt).total_seconds() / 3600
                
                if gap_hours > 1.0:
                    rest_time = gap_hours - 1
                    if rest_time < 6:
                        score -= (6 - rest_time) * config.REST_PENALTY
                    elif rest_time < 16:
                        score -= config.SHORT_REST_PENALTY
                    elif rest_time >= 24:
                        score += config.LONG_REST_BONUS
        return score

    def is_hard_constraint(self) -> bool:
        return False

    def validate(self, slot, context) -> bool:
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.get_type_id()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RestConstraint':
        return cls()
