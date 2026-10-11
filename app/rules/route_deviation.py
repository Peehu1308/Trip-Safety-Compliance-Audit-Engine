from app.rules.base import Rule
from app.domain.dtos import TripContext, ViolationCandidate
from app.domain.enums import ViolationType
from app.rules.enrichment import build_samples
from app.geo.runs import find_runs
from app.geo.polyline import haversine_m

class RouteDeviationRule(Rule):
    code = "ROUTE_DEVIATION"

    def evaluate(self, ctx: TripContext) -> list[ViolationCandidate]:
        samples = build_samples(ctx)
        
        runs = find_runs(
            samples,
            is_bad=lambda s: s.deviation_m > ctx.config.deviation_threshold_m,
            min_duration_s=ctx.config.deviation_min_seconds,
            max_gap_s=ctx.config.max_gps_gap_seconds
        )
        
        candidates = []
        for run in runs:
            seg = samples[run.start_idx : run.end_idx + 1]
            
            # Optional: check deviation_min_meters
            if ctx.config.deviation_min_meters > 0:
                path_length = 0.0
                for i in range(len(seg) - 1):
                    path_length += haversine_m(seg[i].lat, seg[i].lng, seg[i+1].lat, seg[i+1].lng)
                if path_length < ctx.config.deviation_min_meters:
                    continue
                    
            max_dev = max(s.deviation_m for s in seg)
            min_seg_idx = min(s.segment_idx for s in seg)
            max_seg_idx = max(s.segment_idx for s in seg)
            
            epoch_ms = int(run.start_ts.timestamp() * 1000)
            
            candidates.append(
                ViolationCandidate(
                    type=ViolationType.ROUTE_DEVIATION,
                    subject_key=f"run:{epoch_ms}",
                    details={
                        "start_ts": run.start_ts.isoformat(),
                        "end_ts": run.end_ts.isoformat(),
                        "duration_s": run.duration_s,
                        "max_deviation_m": round(max_dev, 1),
                        "start": {"lat": round(seg[0].lat, 4), "lng": round(seg[0].lng, 4)},
                        "end": {"lat": round(seg[-1].lat, 4), "lng": round(seg[-1].lng, 4)},
                        "planned_segment_range": [min_seg_idx, max_seg_idx]
                    }
                )
            )
            
        return candidates
