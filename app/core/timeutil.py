from datetime import datetime, timezone
import zoneinfo

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

def to_local(dt: datetime, tz_name: str) -> datetime:
    tz = zoneinfo.ZoneInfo(tz_name)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)

def is_night(dt: datetime, tz_name: str, night_start_str: str, night_end_str: str) -> bool:
    local_dt = to_local(dt, tz_name)
    t = local_dt.time()
    
    start_hour, start_min = map(int, night_start_str.split(":"))
    end_hour, end_min = map(int, night_end_str.split(":"))
    
    start_mins = start_hour * 60 + start_min
    end_mins = end_hour * 60 + end_min
    t_mins = t.hour * 60 + t.minute
    
    if start_mins <= end_mins:
        return start_mins <= t_mins < end_mins
    else:
        return start_mins <= t_mins or t_mins < end_mins
