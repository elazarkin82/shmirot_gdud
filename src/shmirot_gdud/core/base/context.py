from typing import Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field

@dataclass
class ScheduleContext:
    """
    Holds the global state of the schedule and provides helper methods for constraints.
    Passed to constraints during validation and scoring.
    """
    # Reference to the full schedule slots map (date, hour, pos) -> Slot
    slot_map: Dict[Tuple[str, int, int], Any]
    
    # Usage counters for capacity constraints: (constraint_uid) -> count
    usage_counters: Dict[str, int] = field(default_factory=dict)
    
    # Context specific fields for validation
    group_id: Optional[str] = None
    other_group_id: Optional[str] = None
    is_initial_fill: bool = False
    
    # Helper to get the other slot in the same hour
    def get_other_slot(self, slot: Any) -> Optional[Any]:
        other_pos = 2 if slot.position == 1 else 1
        return self.slot_map.get((slot.date, slot.hour, other_pos))

    def get_usage(self, constraint_uid: str) -> int:
        return self.usage_counters.get(constraint_uid, 0)

    def update_usage(self, constraint_uid: str, delta: int):
        self.usage_counters[constraint_uid] = self.usage_counters.get(constraint_uid, 0) + delta
