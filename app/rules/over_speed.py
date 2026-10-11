from app.rules.base import Rule
from app.domain.dtos import TripContext, ViolationCandidate
from app.domain.enums import ViolationType
from app.rules.enrichment import build_samples
from app.geo.runs import find_runs

class OverSpeedRule(Rule):
    code = "OVER_SPEED"

    def evaluate(self, ctx: TripContext) -> list[ViolationCandidate]:
        samples = build_samples(ctx)
        
        extreme_runs = find_runs(
            samples,
            lambda s: s.speed_kmph > s.limit_kmph + ctx.config.extreme_overspeed_delta_kmph,
            ctx.config.extreme_overspeed_min_seconds,
            ctx.config.max_gps_gap_seconds
        )
        
        normal_runs = find_runs(
            samples,
            lambda s: s.speed_kmph > s.limit_kmph,
            ctx.config.overspeed_min_seconds,
            ctx.config.max_gps_gap_seconds
        )
        
        candidates = []
        
        extreme_intervals = []
        for run in extreme_runs:
            extreme_intervals.append((run.start_ts, run.end_ts))
            
            epoch_ms = int(run.start_ts.timestamp() * 1000)
            seg = samples[run.start_idx : run.end_idx + 1]
            max_speed = max(s.speed_kmph for s in seg)
            limit = seg[0].limit_kmph
            planned_seg = seg[0].segment_idx
            
            candidates.append(
                ViolationCandidate(
                    type=ViolationType.EXTREME_OVER_SPEED,
                    subject_key=f"run:{epoch_ms}",
                    details={
                        "start_ts": run.start_ts.isoformat(),
                        "end_ts": run.end_ts.isoformat(),
                        "duration_s": run.duration_s,
                        "max_speed_kmph": max_speed,
                        "limit_kmph": limit,
                        "planned_segment_idx": planned_seg
                    }
                )
            )
            
        for run in normal_runs:
            # Check if this run contains or overlaps with any extreme run
            overlaps = False
            for ext_start, ext_end in extreme_intervals:
                if run.start_ts <= ext_end and run.end_ts >= ext_start:
                    overlaps = True
                    break
                    
            if not overlaps:
                epoch_ms = int(run.start_ts.timestamp() * 1000)
                seg = samples[run.start_idx : run.end_idx + 1]
                max_speed = max(s.speed_kmph for s in seg)
                limit = seg[0].limit_kmph
                planned_seg = seg[0].segment_idx
                
                candidates.append(
                    ViolationCandidate(
                        type=ViolationType.OVER_SPEED,
                        subject_key=f"run:{epoch_ms}",
                        details={
                            "start_ts": run.start_ts.isoformat(),
                            "end_ts": run.end_ts.isoformat(),
                            "duration_s": run.duration_s,
                            "max_speed_kmph": max_speed,
                            "limit_kmph": limit,
                            "planned_segment_idx": planned_seg
                        }
                    )
                )
                
        return candidates
