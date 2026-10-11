from enum import Enum, IntEnum

class Role(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    DRIVER = "DRIVER"
    ADMIN = "ADMIN"
    APPROVER = "APPROVER"

class Gender(str, Enum):
    F = "F"
    M = "M"
    O = "O"

class StopType(str, Enum):
    PICKUP = "PICKUP"
    DROP = "DROP"

class StopStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FROZEN = "FROZEN"

class TripStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class ViolationType(str, Enum):
    NIGHT_SAFETY = "NIGHT_SAFETY"
    OTP_MISMATCH = "OTP_MISMATCH"
    ROUTE_DEVIATION = "ROUTE_DEVIATION"
    OVER_SPEED = "OVER_SPEED"
    EXTREME_OVER_SPEED = "EXTREME_OVER_SPEED"
    SOS = "SOS"

class Severity(IntEnum):
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3

class ViolationStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"

class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
