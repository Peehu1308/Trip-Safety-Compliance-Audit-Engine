"""
app/core/cache.py
TTLCache wrappers for route and employee caching per SPEC 12.4.
"""
from __future__ import annotations

from typing import Optional, Tuple, List
from cachetools import TTLCache

from app.core.config import settings
from app.core.metrics import cache_requests_total
from app.domain.dtos import EmployeeDTO
from app.geo.polyline import Polyline

# In-memory TTL caches per SPEC 12.4
route_cache: TTLCache[int, Tuple[Optional[Polyline], Optional[List[int]]]] = TTLCache(
    maxsize=settings.CACHE_MAX,
    ttl=settings.CACHE_TTL_S,
)

employee_cache: TTLCache[int, EmployeeDTO] = TTLCache(
    maxsize=settings.CACHE_MAX,
    ttl=settings.CACHE_TTL_S,
)


def get_cached_route(trip_id: int) -> Optional[Tuple[Optional[Polyline], Optional[List[int]]]]:
    """Retrieve cached (Polyline, limits) or None, emitting cache metrics."""
    if trip_id in route_cache:
        cache_requests_total.labels(cache="route", result="hit").inc()
        return route_cache[trip_id]
    cache_requests_total.labels(cache="route", result="miss").inc()
    return None


def set_cached_route(trip_id: int, polyline: Optional[Polyline], limits: Optional[List[int]]) -> None:
    """Store (Polyline, limits) in route cache."""
    route_cache[trip_id] = (polyline, limits)


def get_cached_employee(employee_id: int) -> Optional[EmployeeDTO]:
    """Retrieve cached EmployeeDTO or None, emitting cache metrics."""
    if employee_id in employee_cache:
        cache_requests_total.labels(cache="employee", result="hit").inc()
        return employee_cache[employee_id]
    cache_requests_total.labels(cache="employee", result="miss").inc()
    return None


def set_cached_employee(employee_id: int, employee_dto: EmployeeDTO) -> None:
    """Store EmployeeDTO in employee cache."""
    employee_cache[employee_id] = employee_dto


def invalidate_trip(trip_id: int) -> None:
    """Evict a trip from route_cache."""
    route_cache.pop(trip_id, None)


def invalidate_employee(employee_id: int) -> None:
    """Evict an employee from employee_cache."""
    employee_cache.pop(employee_id, None)


def clear_all_caches() -> None:
    """Clear all caches."""
    route_cache.clear()
    employee_cache.clear()
