"""
app/actions/base.py
Action layer ABCs per SPEC section 9.
No DB imports that pull SQLAlchemy in the ABC signature types — the concrete
implementations in the same package DO import SQLAlchemy; that is intentional
(actions are not in app/domain, app/geo or app/rules).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Optional


@dataclass(frozen=True)
class AlertPayload:
    """PII-free alert payload sent to notification channels."""
    violation_id: int
    trip_id: int
    type: str
    severity: str
    employee_ref: Optional[str]        # opaque e.g. "EMP-12", never a name
    location: Optional[dict]           # cab/SOS location only, rounded
    occurred_at: str                   # ISO-8601 UTC
    summary: str                       # generic text, no PII


class NotificationChannel(ABC):
    """Sends an alert to one channel (log / manager / pager / dashboard)."""
    name: ClassVar[str]

    @abstractmethod
    def send(self, alert: AlertPayload) -> None:
        """Raise on failure; the dispatcher catches and marks FAILED."""
        ...


class StateAction(ABC):
    """
    Runs INSIDE the write transaction; must be idempotent.
    Receives the ORM Violation row (already flushed, not yet committed).
    """

    @abstractmethod
    def applies_to(self, v: object) -> bool:  # v: Violation ORM row
        ...

    @abstractmethod
    def execute(self, session: object, v: object) -> None:
        ...
