"""
app/actions/channels.py
Notification channel implementations.
FAIL_CHANNELS: a set of channel names that will raise on send()
– populated by tests via channels.FAIL_CHANNELS.add(name).
"""
import logging
from typing import ClassVar
from app.actions.base import NotificationChannel, AlertPayload

log = logging.getLogger(__name__)

# Test hook: any channel name added here will raise during send()
FAIL_CHANNELS: set[str] = set()


class LogChannel(NotificationChannel):
    """Writes a structured log line. Never fails."""
    name: ClassVar[str] = "log"

    def send(self, alert: AlertPayload) -> None:
        if self.name in FAIL_CHANNELS:
            raise RuntimeError(f"Forced failure in {self.name}")
        log.info(
            "ALERT",
            extra={
                "violation_id": alert.violation_id,
                "trip_id": alert.trip_id,
                "type": alert.type,
                "severity": alert.severity,
                "employee_ref": alert.employee_ref,
                "occurred_at": alert.occurred_at,
                "summary": alert.summary,
            },
        )


class ManagerChannel(NotificationChannel):
    """Stub: notifies the transport manager (logs + returns)."""
    name: ClassVar[str] = "manager"

    def send(self, alert: AlertPayload) -> None:
        if self.name in FAIL_CHANNELS:
            raise RuntimeError(f"Forced failure in {self.name}")
        log.info("MANAGER_NOTIFY trip=%s type=%s sev=%s", alert.trip_id, alert.type, alert.severity)


class SecurityPagerChannel(NotificationChannel):
    """Stub: pages the security team (logs + returns)."""
    name: ClassVar[str] = "security_pager"

    def send(self, alert: AlertPayload) -> None:
        if self.name in FAIL_CHANNELS:
            raise RuntimeError(f"Forced failure in {self.name}")
        log.info("SECURITY_PAGE trip=%s type=%s", alert.trip_id, alert.type)


class DashboardChannel(NotificationChannel):
    """Stub: pushes a dashboard event (logs + returns)."""
    name: ClassVar[str] = "dashboard"

    def send(self, alert: AlertPayload) -> None:
        if self.name in FAIL_CHANNELS:
            raise RuntimeError(f"Forced failure in {self.name}")
        log.info("DASHBOARD_EVENT trip=%s type=%s sev=%s", alert.trip_id, alert.type, alert.severity)


# Registry used by router and dispatcher
CHANNEL_REGISTRY: dict[str, NotificationChannel] = {
    ch.name: ch
    for ch in [LogChannel(), ManagerChannel(), SecurityPagerChannel(), DashboardChannel()]
}
