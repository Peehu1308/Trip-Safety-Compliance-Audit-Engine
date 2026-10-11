from dataclasses import dataclass
from typing import Sequence, Callable
from datetime import datetime
from app.domain.dtos import Sample

@dataclass(frozen=True)
class Run:
    start_idx: int
    end_idx: int          # inclusive, indices into the samples list
    start_ts: datetime
    end_ts: datetime
    duration_s: float     # end_ts - start_ts (first bad fix -> last bad fix)

def find_runs(samples: Sequence[Sample],
              is_bad: Callable[[Sample], bool],
              min_duration_s: float,
              max_gap_s: float) -> list[Run]:
    """
    Input MUST be sorted by ts.
    """
    runs = []
    
    start_idx = -1
    last_bad_idx = -1
    
    for i, s in enumerate(samples):
        bad = is_bad(s)
        
        if bad:
            if start_idx == -1:
                start_idx = i
                last_bad_idx = i
            else:
                gap = (s.ts - samples[last_bad_idx].ts).total_seconds()
                if gap <= max_gap_s:
                    last_bad_idx = i
                else:
                    # Close old run
                    dur = (samples[last_bad_idx].ts - samples[start_idx].ts).total_seconds()
                    if dur >= min_duration_s and start_idx != last_bad_idx:
                        runs.append(Run(start_idx, last_bad_idx, samples[start_idx].ts, samples[last_bad_idx].ts, dur))
                    # Open new run
                    start_idx = i
                    last_bad_idx = i
        else:
            if start_idx != -1:
                # Close run
                dur = (samples[last_bad_idx].ts - samples[start_idx].ts).total_seconds()
                if dur >= min_duration_s and start_idx != last_bad_idx:
                    runs.append(Run(start_idx, last_bad_idx, samples[start_idx].ts, samples[last_bad_idx].ts, dur))
                start_idx = -1
                last_bad_idx = -1
                
    if start_idx != -1:
        dur = (samples[last_bad_idx].ts - samples[start_idx].ts).total_seconds()
        if dur >= min_duration_s and start_idx != last_bad_idx:
            runs.append(Run(start_idx, last_bad_idx, samples[start_idx].ts, samples[last_bad_idx].ts, dur))
            
    return runs
