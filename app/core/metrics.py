"""
app/core/metrics.py
Prometheus metrics registry per SPEC 12.3.
"""
from prometheus_client import Counter, Histogram, Gauge

violations_total = Counter("violations_total", "Total violations", ["type", "severity"])
audits_total = Counter("audits_total", "Total audits", ["result"])
audit_duplicates_skipped_total = Counter("audit_duplicates_skipped_total", "Duplicates skipped in audit")
otp_attempts_total = Counter("otp_attempts_total", "OTP attempts", ["result"])
sos_total = Counter("sos_total", "Total SOS events")
notifications_total = Counter("notifications_total", "Notifications sent", ["channel", "status"])
rule_errors_total = Counter("rule_errors_total", "Rule evaluation errors", ["rule"])
auth_failures_total = Counter("auth_failures_total", "Failed authentication attempts")
cache_requests_total = Counter("cache_requests_total", "Cache requests", ["cache", "result"])
http_requests_total = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
audit_duration_seconds = Histogram("audit_duration_seconds", "Audit duration in seconds")

outbox_pending = Gauge("outbox_pending", "Pending outbox notifications")


def _get_outbox_pending() -> int:
    try:
        import app.core.db as db_mod
        import app.repositories.outbox_repo as outbox_repo
        with db_mod.SessionLocal() as session:
            return outbox_repo.count_pending(session)
    except Exception:
        return 0


outbox_pending.set_function(_get_outbox_pending)
