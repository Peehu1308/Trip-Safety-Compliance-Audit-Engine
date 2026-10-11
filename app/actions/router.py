"""
app/actions/router.py
Config-driven routing from severity → channels and violation type → state actions.
"""
from app.domain.enums import Severity
from app.actions.state_actions import RequireEscortAction
from app.actions.base import StateAction

CHANNELS_BY_SEVERITY: dict[int, list[str]] = {
    Severity.CRITICAL: ["security_pager", "manager", "log"],
    Severity.HIGH:     ["manager", "log"],
    Severity.MEDIUM:   ["dashboard", "log"],
}


class ActionRouter:
    """Routes a violation to the correct channels and state actions."""

    _state_actions: list[StateAction] = [RequireEscortAction()]

    def channels_for(self, severity: int) -> list[str]:
        """Return channel names for the given Severity int."""
        return CHANNELS_BY_SEVERITY.get(int(severity), ["log"])

    def state_actions_for(self, v: object) -> list[StateAction]:
        """Return all state actions that apply to this violation row."""
        return [a for a in self._state_actions if a.applies_to(v)]


router = ActionRouter()
