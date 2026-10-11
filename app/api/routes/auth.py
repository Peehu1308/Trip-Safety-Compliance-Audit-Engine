"""
app/api/routes/auth.py
Authentication routes: login and me.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
import app.services.auth_service as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Public login endpoint returning JWT access token."""
    return auth_service.login(db, req.username, req.password)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return profile for currently authenticated user."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
    )
