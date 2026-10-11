"""
app/schemas/auth.py
Pydantic schemas for authentication and user endpoints.
"""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class UserResponse(BaseModel):
    id: int
    username: str
    role: str

    model_config = ConfigDict(from_attributes=True)
