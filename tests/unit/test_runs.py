from datetime import datetime, timedelta
from app.geo.runs import find_runs
from app.domain.dtos import Sample

def make_sample(ts, bad):
    return Sample(ts=ts, lat=0, lng=0, speed_kmph=0, deviation_m=1000 if bad else 0, segment_idx=0, limit_kmph=0)

def test_single_fix_blip():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    samples = [
        make_sample(t0, False),
        make_sample(t0 + timedelta(seconds=15), True),
        make_sample(t0 + timedelta(seconds=30), False),
    ]
    runs = find_runs(samples, lambda s: s.deviation_m > 500, 120, 90)
    assert len(runs) == 0

def test_17_fixes_run():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    samples = [make_sample(t0 + timedelta(seconds=i*15), True) for i in range(17)]
    runs = find_runs(samples, lambda s: s.deviation_m > 500, 120, 90)
    assert len(runs) == 1
    assert runs[0].duration_s == 240
    assert runs[0].start_idx == 0
    assert runs[0].end_idx == 16

def test_gap_splits_run():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    samples = []
    # 9 fixes = 120s
    for i in range(9):
        samples.append(make_sample(t0 + timedelta(seconds=i*15), True))
    
    # 100s gap (max_gap is 90)
    t1 = samples[-1].ts + timedelta(seconds=100)
    for i in range(9):
        samples.append(make_sample(t1 + timedelta(seconds=i*15), True))
        
    runs = find_runs(samples, lambda s: s.deviation_m > 500, 120, 90)
    assert len(runs) == 2
    assert runs[0].duration_s == 120
    assert runs[1].duration_s == 120

def test_good_fix_splits():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    samples = []
    for i in range(9):
        samples.append(make_sample(t0 + timedelta(seconds=i*15), True))
    
    samples.append(make_sample(samples[-1].ts + timedelta(seconds=15), False))
    
    t1 = samples[-1].ts + timedelta(seconds=15)
    for i in range(9):
        samples.append(make_sample(t1 + timedelta(seconds=i*15), True))
        
    runs = find_runs(samples, lambda s: s.deviation_m > 500, 120, 90)
    assert len(runs) == 2

def test_min_duration_boundary():
    t0 = datetime(2023, 1, 1, 10, 0, 0)
    samples = []
    for i in range(9): # 8 intervals of 15s = 120s
        samples.append(make_sample(t0 + timedelta(seconds=i*15), True))
        
    runs = find_runs(samples, lambda s: s.deviation_m > 500, 120, 90)
    assert len(runs) == 1
    assert runs[0].duration_s == 120
