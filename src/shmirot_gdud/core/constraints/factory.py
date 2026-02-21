from typing import Dict, Any, Type
from shmirot_gdud.core.base.constraint import ConstraintBase
from shmirot_gdud.core.constraints.implementations import (
    UnavailabilityConstraint,
    ActivityWindowConstraint,
    DateSpecificConstraint,
    StaffingRuleConstraint,
    SimultaneousConstraint,
    ConsecutiveConstraint,
    RestConstraint
)

class ConstraintFactory:
    _registry: Dict[str, Type[ConstraintBase]] = {
        "unavailability": UnavailabilityConstraint,
        "activity_window": ActivityWindowConstraint,
        "date_specific": DateSpecificConstraint,
        "staffing_rules": StaffingRuleConstraint,
        "simultaneous": SimultaneousConstraint,
        "consecutive": ConsecutiveConstraint,
        "rest": RestConstraint
    }

    @classmethod
    def create_from_dict(cls, data: Dict[str, Any]) -> ConstraintBase:
        type_id = data.get("type")
        constraint_class = cls._registry.get(type_id)
        if constraint_class:
            return constraint_class.from_dict(data)
        raise ValueError(f"Unknown constraint type: {type_id}")
