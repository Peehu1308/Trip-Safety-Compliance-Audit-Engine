"""
app/repositories/user_repo.py
DB access for User, Employee, Driver, and Vehicle rows.
"""
from __future__ import annotations
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.user import User
from app.models.people import Employee, Driver, Vehicle


def get_by_id(session: Session, user_id: int) -> Optional[User]:
    return session.get(User, user_id)


def get_by_username(session: Session, username: str) -> Optional[User]:
    return session.scalar(select(User).where(User.username == username))


def get_employee_by_user_id(session: Session, user_id: int) -> Optional[Employee]:
    return session.scalar(select(Employee).where(Employee.user_id == user_id))


def get_employee_by_id(session: Session, employee_id: int) -> Optional[Employee]:
    return session.get(Employee, employee_id)


def get_driver_by_user_id(session: Session, user_id: int) -> Optional[Driver]:
    return session.scalar(select(Driver).where(Driver.user_id == user_id))


def get_driver_by_id(session: Session, driver_id: int) -> Optional[Driver]:
    return session.get(Driver, driver_id)


def get_vehicle_by_id(session: Session, vehicle_id: int) -> Optional[Vehicle]:
    return session.get(Vehicle, vehicle_id)
