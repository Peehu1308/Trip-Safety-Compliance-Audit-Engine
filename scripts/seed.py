"""
scripts/seed.py
Seeds users, employees, vehicle, driver, and the four demo trips with GPS trails
per SPEC section 13. Deterministic test and demo scenarios.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.core.db import engine as global_engine, SessionLocal
from app.core.security import hash_password
from app.domain.enums import Role, Gender, StopType, StopStatus, TripStatus
from app.geo.polyline import haversine_m
from app.models.base import Base
from app.models.user import User
from app.models.people import Employee, Driver, Vehicle
from app.models.trip import Trip, Stop
from app.models.gps import GpsFix
import app.services.audit_log_service as audit_log_service

log = logging.getLogger(__name__)

DEMO_ROUTE = [
    [28.5355, 77.3000],  # A
    [28.5355, 77.3500],  # B
    [28.5355, 77.4000],  # C
    [28.5355, 77.4500],  # D
]
DEMO_LIMITS = [60, 60, 60]


def make_trail(
    route: List[List[float]],
    start_ts: datetime,
    speed_kmph: float = 40.0,
    interval_s: int = 15,
) -> List[Dict[str, Any]]:
    """
    Interpolate position by distance along the route.
    Produces ~88 fixes for the 14.7 km demo route at 40 km/h with 15s intervals.
    """
    seg_lengths = [
        haversine_m(route[i][0], route[i][1], route[i + 1][0], route[i + 1][1])
        for i in range(len(route) - 1)
    ]
    total_dist = sum(seg_lengths)
    speed_ms = speed_kmph * 1000.0 / 3600.0
    step_m = speed_ms * interval_s

    fixes: List[Dict[str, Any]] = []
    for i in range(88):
        curr_dist = min(i * step_m, total_dist)

        # Locate segment
        accum = 0.0
        sidx = 0
        while sidx < len(seg_lengths) - 1 and accum + seg_lengths[sidx] < curr_dist:
            accum += seg_lengths[sidx]
            sidx += 1

        seg_len = seg_lengths[sidx]
        frac = (curr_dist - accum) / seg_len if seg_len > 0 else 0.0
        frac = max(0.0, min(1.0, frac))

        lat = route[sidx][0] + frac * (route[sidx + 1][0] - route[sidx][0])
        lng = route[sidx][1] + frac * (route[sidx + 1][1] - route[sidx][1])

        ts = start_ts + timedelta(seconds=i * interval_s)
        fixes.append({
            "ts": ts,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "speed_kmph": round(speed_kmph, 1),
        })

    return fixes


def seed(session: Optional[Session] = None, bind_engine=None) -> Dict[str, Any]:
    """
    Seed database with SPEC 13 users, vehicle, driver, employees, and 4 demo trips.
    """
    active_engine = bind_engine or global_engine
    Base.metadata.create_all(bind_engine or active_engine)

    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    try:
        # 1. Users per SPEC 13
        users_meta = [
            ("admin", "Admin@123", Role.ADMIN),
            ("approver1", "Approver@123", Role.APPROVER),
            ("driver1", "Driver@123", Role.DRIVER),
            ("priya", "Emp@123", Role.EMPLOYEE),
            ("rahul", "Emp@123", Role.EMPLOYEE),
            ("anita", "Emp@123", Role.EMPLOYEE),
            ("vikram", "Emp@123", Role.EMPLOYEE),
        ]

        users_by_name: Dict[str, User] = {}
        for username, password, role in users_meta:
            existing = session.query(User).filter_by(username=username).first()
            if not existing:
                u = User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                    is_active=True,
                    created_at=datetime(2026, 10, 1, 0, 0),
                )
                session.add(u)
                session.flush()
                users_by_name[username] = u
            else:
                users_by_name[username] = existing

        # 2. Driver & Vehicle
        driver = session.query(Driver).filter_by(user_id=users_by_name["driver1"].id).first()
        if not driver:
            driver = Driver(user_id=users_by_name["driver1"].id, name="Driver One", license_no="DL-01-2024-001")
            session.add(driver)
            session.flush()

        vehicle = session.query(Vehicle).filter_by(reg_no="KA01AB1234").first()
        if not vehicle:
            vehicle = Vehicle(reg_no="KA01AB1234", model="Toyota Innova")
            session.add(vehicle)
            session.flush()

        # 3. Employees
        emp_meta = [
            ("priya", "Priya Sharma", Gender.F, "9876543210"),
            ("rahul", "Rahul Verma", Gender.M, "9876543211"),
            ("anita", "Anita Rao", Gender.F, "9876543212"),
            ("vikram", "Vikram Singh", Gender.M, "9876543213"),
        ]
        employees_by_name: Dict[str, Employee] = {}
        for uname, name, gender, phone in emp_meta:
            emp = session.query(Employee).filter_by(user_id=users_by_name[uname].id).first()
            if not emp:
                emp = Employee(user_id=users_by_name[uname].id, name=name, gender=gender, phone=phone)
                session.add(emp)
                session.flush()
            employees_by_name[uname] = emp

        # Check if trips already seeded
        existing_trips = session.query(Trip).all()
        if existing_trips:
            session.commit()
            return {
                "users": users_by_name,
                "driver": driver,
                "vehicle": vehicle,
                "employees": employees_by_name,
                "trips": existing_trips,
            }

        created_trips: List[Trip] = []

        # -------------------------------------------------------------------
        # TRIP 1: Night, female last drop
        # Date 2026-10-09 IST.
        # Stops: P(Rahul 22:15 IST = 16:45 UTC), P(Priya 22:40 IST = 17:10 UTC),
        #        D(Rahul 23:00 IST = 17:30 UTC), D(Priya 23:10 IST = 17:40 UTC)
        # escort_assigned=false. Clean trail.
        # Expected audit: exactly 1 x NIGHT_SAFETY (HIGH), reason LAST_DROP
        # -------------------------------------------------------------------
        t1 = Trip(
            id=1,
            driver_id=driver.id,
            vehicle_id=vehicle.id,
            status=TripStatus.SCHEDULED,
            escort_assigned=False,
            requires_escort=False,
            planned_route=DEMO_ROUTE,
            segment_speed_limits=DEMO_LIMITS,
            default_speed_limit_kmph=60,
            created_at=datetime(2026, 10, 9, 16, 0),
        )
        session.add(t1)
        session.flush()

        t1_stops = [
            Stop(trip_id=1, sequence=1, type=StopType.PICKUP, employee_id=employees_by_name["rahul"].id,
                 planned_time=datetime(2026, 10, 9, 16, 45), lat=28.5355, lng=77.3000, status=StopStatus.PENDING),
            Stop(trip_id=1, sequence=2, type=StopType.PICKUP, employee_id=employees_by_name["priya"].id,
                 planned_time=datetime(2026, 10, 9, 17, 10), lat=28.5355, lng=77.3500, status=StopStatus.PENDING),
            Stop(trip_id=1, sequence=3, type=StopType.DROP, employee_id=employees_by_name["rahul"].id,
                 planned_time=datetime(2026, 10, 9, 17, 30), lat=28.5355, lng=77.4000, status=StopStatus.PENDING),
            Stop(trip_id=1, sequence=4, type=StopType.DROP, employee_id=employees_by_name["priya"].id,
                 planned_time=datetime(2026, 10, 9, 17, 40), lat=28.5355, lng=77.4500, status=StopStatus.PENDING),
        ]
        session.add_all(t1_stops)
        session.flush()

        t1_fixes_data = make_trail(DEMO_ROUTE, start_ts=datetime(2026, 10, 9, 16, 45), speed_kmph=40.0)
        session.add_all([GpsFix(trip_id=1, **f) for f in t1_fixes_data])
        audit_log_service.append(session, "admin", "ADMIN", "TRIP_CREATED", "trip", 1, {"driver_id": driver.id, "stops": 4})
        created_trips.append(t1)

        # -------------------------------------------------------------------
        # TRIP 2: Route deviation
        # Day trip 14:00 IST = 08:30 UTC.
        # Fix #15 shifted +0.0108 lat (~1.2 km blip)
        # Fixes #40 to #56 shifted +0.0076 lat (~845 m sustained 240 s)
        # Expected: exactly 1 x ROUTE_DEVIATION (HIGH), max_deviation_m ≈ 845, duration_s = 240
        # -------------------------------------------------------------------
        t2 = Trip(
            id=2,
            driver_id=driver.id,
            vehicle_id=vehicle.id,
            status=TripStatus.SCHEDULED,
            escort_assigned=False,
            requires_escort=False,
            planned_route=DEMO_ROUTE,
            segment_speed_limits=DEMO_LIMITS,
            default_speed_limit_kmph=60,
            created_at=datetime(2026, 10, 9, 8, 0),
        )
        session.add(t2)
        session.flush()

        t2_stops = [
            Stop(trip_id=2, sequence=1, type=StopType.PICKUP, employee_id=employees_by_name["rahul"].id,
                 planned_time=datetime(2026, 10, 9, 8, 30), lat=28.5355, lng=77.3000, status=StopStatus.PENDING),
            Stop(trip_id=2, sequence=2, type=StopType.PICKUP, employee_id=employees_by_name["vikram"].id,
                 planned_time=datetime(2026, 10, 9, 8, 35), lat=28.5355, lng=77.3500, status=StopStatus.PENDING),
            Stop(trip_id=2, sequence=3, type=StopType.DROP, employee_id=employees_by_name["rahul"].id,
                 planned_time=datetime(2026, 10, 9, 8, 50), lat=28.5355, lng=77.4000, status=StopStatus.PENDING),
            Stop(trip_id=2, sequence=4, type=StopType.DROP, employee_id=employees_by_name["vikram"].id,
                 planned_time=datetime(2026, 10, 9, 9, 0), lat=28.5355, lng=77.4500, status=StopStatus.PENDING),
        ]
        session.add_all(t2_stops)
        session.flush()

        t2_fixes_data = make_trail(DEMO_ROUTE, start_ts=datetime(2026, 10, 9, 8, 30), speed_kmph=40.0)
        # Apply edits
        t2_fixes_data[15]["lat"] = round(t2_fixes_data[15]["lat"] + 0.0108, 6)
        for idx in range(40, 57):
            t2_fixes_data[idx]["lat"] = round(t2_fixes_data[idx]["lat"] + 0.0076, 6)

        session.add_all([GpsFix(trip_id=2, **f) for f in t2_fixes_data])
        audit_log_service.append(session, "admin", "ADMIN", "TRIP_CREATED", "trip", 2, {"driver_id": driver.id, "stops": 4})
        created_trips.append(t2)

        # -------------------------------------------------------------------
        # TRIP 3: Over-speed
        # Day trip 10:00 IST = 04:30 UTC.
        # Fix #10 speed 95 (single spike).
        # Fixes #20 to #23 (4 fixes, 45 s) speed 75.
        # Fixes #50 to #52 (3 fixes, 30 s) speed 110.
        # Expected: 1 x OVER_SPEED (MEDIUM, 45 s, max 75) + 1 x EXTREME_OVER_SPEED (CRITICAL, 30 s)
        # -------------------------------------------------------------------
        t3 = Trip(
            id=3,
            driver_id=driver.id,
            vehicle_id=vehicle.id,
            status=TripStatus.SCHEDULED,
            escort_assigned=False,
            requires_escort=False,
            planned_route=DEMO_ROUTE,
            segment_speed_limits=DEMO_LIMITS,
            default_speed_limit_kmph=60,
            created_at=datetime(2026, 10, 9, 4, 0),
        )
        session.add(t3)
        session.flush()

        t3_stops = [
            Stop(trip_id=3, sequence=1, type=StopType.PICKUP, employee_id=employees_by_name["rahul"].id,
                 planned_time=datetime(2026, 10, 9, 4, 30), lat=28.5355, lng=77.3000, status=StopStatus.PENDING),
            Stop(trip_id=3, sequence=2, type=StopType.PICKUP, employee_id=employees_by_name["vikram"].id,
                 planned_time=datetime(2026, 10, 9, 4, 35), lat=28.5355, lng=77.3500, status=StopStatus.PENDING),
            Stop(trip_id=3, sequence=3, type=StopType.DROP, employee_id=employees_by_name["rahul"].id,
                 planned_time=datetime(2026, 10, 9, 4, 50), lat=28.5355, lng=77.4000, status=StopStatus.PENDING),
            Stop(trip_id=3, sequence=4, type=StopType.DROP, employee_id=employees_by_name["vikram"].id,
                 planned_time=datetime(2026, 10, 9, 5, 0), lat=28.5355, lng=77.4500, status=StopStatus.PENDING),
        ]
        session.add_all(t3_stops)
        session.flush()

        t3_fixes_data = make_trail(DEMO_ROUTE, start_ts=datetime(2026, 10, 9, 4, 30), speed_kmph=40.0)
        # Apply edits
        t3_fixes_data[10]["speed_kmph"] = 95.0
        for idx in range(20, 24):
            t3_fixes_data[idx]["speed_kmph"] = 75.0
        for idx in range(50, 53):
            t3_fixes_data[idx]["speed_kmph"] = 110.0

        session.add_all([GpsFix(trip_id=3, **f) for f in t3_fixes_data])
        audit_log_service.append(session, "admin", "ADMIN", "TRIP_CREATED", "trip", 3, {"driver_id": driver.id, "stops": 4})
        created_trips.append(t3)

        # -------------------------------------------------------------------
        # TRIP 4: Clean control
        # Day trip, men only or escorted, clean trail.
        # Expected: 0 violations.
        # -------------------------------------------------------------------
        t4 = Trip(
            id=4,
            driver_id=driver.id,
            vehicle_id=vehicle.id,
            status=TripStatus.SCHEDULED,
            escort_assigned=True,
            requires_escort=False,
            planned_route=DEMO_ROUTE,
            segment_speed_limits=DEMO_LIMITS,
            default_speed_limit_kmph=60,
            created_at=datetime(2026, 10, 9, 5, 0),
        )
        session.add(t4)
        session.flush()

        t4_stops = [
            Stop(trip_id=4, sequence=1, type=StopType.PICKUP, employee_id=employees_by_name["rahul"].id,
                 planned_time=datetime(2026, 10, 9, 5, 30), lat=28.5355, lng=77.3000, status=StopStatus.PENDING),
            Stop(trip_id=4, sequence=2, type=StopType.PICKUP, employee_id=employees_by_name["vikram"].id,
                 planned_time=datetime(2026, 10, 9, 5, 35), lat=28.5355, lng=77.3500, status=StopStatus.PENDING),
            Stop(trip_id=4, sequence=3, type=StopType.DROP, employee_id=employees_by_name["rahul"].id,
                 planned_time=datetime(2026, 10, 9, 5, 50), lat=28.5355, lng=77.4000, status=StopStatus.PENDING),
            Stop(trip_id=4, sequence=4, type=StopType.DROP, employee_id=employees_by_name["vikram"].id,
                 planned_time=datetime(2026, 10, 9, 6, 0), lat=28.5355, lng=77.4500, status=StopStatus.PENDING),
        ]
        session.add_all(t4_stops)
        session.flush()

        t4_fixes_data = make_trail(DEMO_ROUTE, start_ts=datetime(2026, 10, 9, 5, 30), speed_kmph=40.0)
        session.add_all([GpsFix(trip_id=4, **f) for f in t4_fixes_data])
        audit_log_service.append(session, "admin", "ADMIN", "TRIP_CREATED", "trip", 4, {"driver_id": driver.id, "stops": 4})
        created_trips.append(t4)

        session.commit()
        print("Database seeded successfully with SPEC 13 demo scenarios!")

        return {
            "users": users_by_name,
            "driver": driver,
            "vehicle": vehicle,
            "employees": employees_by_name,
            "trips": created_trips,
        }

    except Exception:
        session.rollback()
        raise
    finally:
        if close_session:
            session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
