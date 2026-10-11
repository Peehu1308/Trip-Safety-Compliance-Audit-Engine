from app.domain.dtos import TripContext, Sample

def build_samples(ctx: TripContext) -> list[Sample]:
    """Sort fixes by ts; for each fix compute (deviation_m, segment_idx) via ctx.polyline.distance_to,
    and limit_kmph = ctx.segment_limits[segment_idx] if provided else ctx.default_limit.
    Return [] if ctx.polyline is None.
    """
    if ctx.polyline is None:
        return []
        
    samples = []
    # Assumes fixes are already sorted or we sort them now. We'll sort to be safe.
    sorted_fixes = sorted(ctx.fixes, key=lambda f: f.ts)
    
    for f in sorted_fixes:
        dist, seg_idx = ctx.polyline.distance_to(f.lat, f.lng)
        
        limit = ctx.default_limit
        if ctx.segment_limits and 0 <= seg_idx < len(ctx.segment_limits):
            limit = ctx.segment_limits[seg_idx]
            
        samples.append(Sample(
            ts=f.ts,
            lat=f.lat,
            lng=f.lng,
            speed_kmph=f.speed_kmph,
            deviation_m=dist,
            segment_idx=seg_idx,
            limit_kmph=limit
        ))
        
    return samples
