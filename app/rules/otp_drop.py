from collections import defaultdict
from app.rules.base import Rule
from app.domain.dtos import TripContext, ViolationCandidate
from app.domain.enums import ViolationType

class OtpDropRule(Rule):
    code = "OTP_MISMATCH"

    def evaluate(self, ctx: TripContext) -> list[ViolationCandidate]:
        events_by_stop = defaultdict(list)
        for e in ctx.otp_events:
            events_by_stop[e.stop_id].append(e)
            
        candidates = []
        for stop_id, events in events_by_stop.items():
            failed_events = [e for e in events if not e.success]
            if failed_events:
                failed_events.sort(key=lambda e: e.ts)
                candidates.append(
                    ViolationCandidate(
                        type=ViolationType.OTP_MISMATCH,
                        subject_key=f"stop:{stop_id}",
                        details={
                            "stop_id": stop_id,
                            "failed_attempts": len(failed_events),
                            "first_failed_at": failed_events[0].ts.isoformat(),
                            "last_failed_at": failed_events[-1].ts.isoformat()
                        }
                    )
                )
        return candidates
