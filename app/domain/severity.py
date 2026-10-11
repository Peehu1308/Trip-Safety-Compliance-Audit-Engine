from app.domain.enums import ViolationType, Severity

SEVERITY_BY_TYPE = {
    ViolationType.SOS: Severity.CRITICAL,
    ViolationType.EXTREME_OVER_SPEED: Severity.CRITICAL,
    ViolationType.ROUTE_DEVIATION: Severity.HIGH,
    ViolationType.OTP_MISMATCH: Severity.HIGH,
    ViolationType.NIGHT_SAFETY: Severity.HIGH,
    ViolationType.OVER_SPEED: Severity.MEDIUM,
}

def severity_for(t: ViolationType) -> Severity:
    return SEVERITY_BY_TYPE[t]
