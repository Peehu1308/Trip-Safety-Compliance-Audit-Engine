from app.domain.enums import ViolationType, Severity
from app.domain.severity import severity_for, SEVERITY_BY_TYPE

def test_severity_mapping():
    assert severity_for(ViolationType.SOS) == Severity.CRITICAL
    assert severity_for(ViolationType.EXTREME_OVER_SPEED) == Severity.CRITICAL
    assert severity_for(ViolationType.ROUTE_DEVIATION) == Severity.HIGH
    assert severity_for(ViolationType.OTP_MISMATCH) == Severity.HIGH
    assert severity_for(ViolationType.NIGHT_SAFETY) == Severity.HIGH
    assert severity_for(ViolationType.OVER_SPEED) == Severity.MEDIUM

def test_all_violation_types_mapped():
    for vt in ViolationType:
        assert vt in SEVERITY_BY_TYPE
