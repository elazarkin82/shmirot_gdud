from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from shmirot_gdud.core.models import ScheduleSlot
    from shmirot_gdud.core.base.context import ScheduleContext

class ConstraintBase(ABC):
    """
    Abstract base class for all constraints.
    """
    
    def __init__(self):
        # Unique ID for state tracking (e.g. usage counters)
        import uuid
        self.uid = str(uuid.uuid4())

    @abstractmethod
    def get_type_id(self) -> str:
        """Returns a unique string identifier for this constraint type."""
        pass

    @abstractmethod
    def get_display_name(self) -> str:
        """Returns the name to display on the button in the GUI."""
        pass

    @abstractmethod
    def get_status_text(self) -> str:
        """Returns a short summary text to display next to the button."""
        pass

    @abstractmethod
    def open_edit_dialog(self, parent, on_save: 'Callable[[ConstraintBase], None]'):
        """Opens the GUI dialog to edit this constraint."""
        pass

    @abstractmethod
    def check_validity(self, slot: 'ScheduleSlot', context: 'ScheduleContext') -> bool:
        """
        Checks if assigning the group to this slot violates a HARD constraint.
        Returns True if valid, False if invalid.
        """
        pass

    @abstractmethod
    def calculate_score(self, slot: 'ScheduleSlot', context: 'ScheduleContext') -> float:
        """
        Calculates the score (bonus/penalty) for this assignment.
        Positive = Good (Bonus), Negative = Bad (Penalty).
        """
        pass
        
    def on_assign(self, slot: 'ScheduleSlot', context: 'ScheduleContext'):
        """Called when the group is assigned to a slot. Update state here."""
        pass
        
    def on_remove(self, slot: 'ScheduleSlot', context: 'ScheduleContext'):
        """Called when the group is removed from a slot. Update state here."""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serializes the constraint to a dictionary."""
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConstraintBase':
        """Deserializes from a dictionary."""
        pass
