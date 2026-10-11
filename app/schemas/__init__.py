"""
app/schemas
Pydantic schemas package.
"""
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.schemas.trips import TripCreate, StopCreate, EscortUpdateRequest, TripResponse, StopResponse
from app.schemas.gps import GpsFixIn, GpsIngestRequest, GpsIngestResponse
from app.schemas.events import OtpSubmitRequest, OtpSubmitResponse, OtpValueResponse, UnfreezeRequest, SosRequest, SosResponse
from app.schemas.violations import ViolationResponse, ViolationAcknowledgeRequest
from app.schemas.audit import AuditResponse, AuditLogResponse, AuditVerifyResponse

__all__ = [
    "LoginRequest", "TokenResponse", "UserResponse",
    "TripCreate", "StopCreate", "EscortUpdateRequest", "TripResponse", "StopResponse",
    "GpsFixIn", "GpsIngestRequest", "GpsIngestResponse",
    "OtpSubmitRequest", "OtpSubmitResponse", "OtpValueResponse", "UnfreezeRequest", "SosRequest", "SosResponse",
    "ViolationResponse", "ViolationAcknowledgeRequest",
    "AuditResponse", "AuditLogResponse", "AuditVerifyResponse",
]
