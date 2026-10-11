from app.rules.base import Rule
from app.domain.dtos import TripContext, ViolationCandidate
from app.domain.enums import ViolationType

class SosRule(Rule):
    code = "SOS"

    def evaluate(self, ctx: TripContext) -> list[ViolationCandidate]:
        candidates = []
        for e in ctx.sos_events:
            emp = ctx.employees.get(e.employee_id)
            emp_ref = emp.ref if emp else f"EMP-{e.employee_id}"
            
            candidates.append(
                ViolationCandidate(
                    type=ViolationType.SOS,
                    subject_key=f"sos:{e.id}",
                    details={
                        "sos_event_id": e.id,
                        "employee_ref": emp_ref,
                        "lat": round(e.lat, ctx.config.sos_decimals) if e.lat is not None else None,
                        "lng": round(e.lng, ctx.config.sos_decimals) if e.lng is not None else None,
                        "ts": e.ts.isoformat()
                    }
                )
            )
        return candidates
