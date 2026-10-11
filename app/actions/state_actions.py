"""
app/actions/state_actions.py
StateAction implementations that run inside the DB transaction.
"""
from app.actions.base import StateAction
from app.domain.enums import ViolationType


class RequireEscortAction(StateAction):
    """Applies to NIGHT_SAFETY; sets trips.requires_escort = True (idempotent)."""

    def applies_to(self, v: object) -> bool:
        v_type = v.type.value if hasattr(v.type, "value") else str(v.type)
        return v_type in ("NIGHT_SAFETY", ViolationType.NIGHT_SAFETY.value, "ViolationType.NIGHT_SAFETY")

    def execute(self, session: object, v: object) -> None:
        from app.models.trip import Trip  # local import to avoid circular at module level
        trip = session.get(Trip, v.trip_id)
        if trip and not trip.requires_escort:
            trip.requires_escort = True
            session.flush()
