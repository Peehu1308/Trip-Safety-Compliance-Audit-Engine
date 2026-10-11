from app.rules.base import Rule
from app.domain.dtos import TripContext, ViolationCandidate
from app.domain.enums import ViolationType, StopType, Gender
from app.core.timeutil import is_night, to_local

class NightSafetyRule(Rule):
    code = "NIGHT_SAFETY"

    def evaluate(self, ctx: TripContext) -> list[ViolationCandidate]:
        if not ctx.stops:
            return []
            
        stops = sorted(ctx.stops, key=lambda s: s.sequence)
        pickups = [s for s in stops if s.type == StopType.PICKUP]
        drops = [s for s in stops if s.type == StopType.DROP]
        
        first_pickup = pickups[0] if pickups else None
        last_drop = drops[-1] if drops else None
        
        candidates = []
        checks = []
        if first_pickup:
            checks.append((first_pickup, "FIRST_PICKUP"))
        if last_drop:
            checks.append((last_drop, "LAST_DROP"))
            
        for stop, reason in checks:
            if stop.employee_id not in ctx.employees:
                continue
                
            emp = ctx.employees[stop.employee_id]
            t = stop.actual_time or stop.planned_time
            
            if emp.gender == Gender.F and is_night(t, ctx.config.local_tz, ctx.config.night_start, ctx.config.night_end) and not ctx.escort_assigned:
                t_local_iso = to_local(t, ctx.config.local_tz).isoformat()
                
                candidates.append(
                    ViolationCandidate(
                        type=ViolationType.NIGHT_SAFETY,
                        subject_key=f"stop:{stop.id}:{reason}",
                        details={
                            "stop_id": stop.id,
                            "sequence": stop.sequence,
                            "reason": reason,
                            "employee_ref": emp.ref,
                            "time_local": t_local_iso,
                            "requires_escort": True
                        }
                    )
                )
                
        return candidates
