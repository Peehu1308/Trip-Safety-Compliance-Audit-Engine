import pytest
import math
from app.geo.polyline import Polyline, haversine_m

def test_haversine_sanity():
    # Delhi to Noida approx 15km
    dist = haversine_m(28.6139, 77.2090, 28.5355, 77.3910)
    assert 15000 < dist < 22000

def test_polyline_less_than_2_points():
    with pytest.raises(ValueError):
        Polyline([(28.0, 77.0)])
    with pytest.raises(ValueError):
        Polyline([])

def test_point_on_line():
    route = Polyline([(28.0, 77.0), (28.0, 77.1)])
    dist, idx = route.distance_to(28.0, 77.05)
    assert math.isclose(dist, 0.0, abs_tol=1e-5)
    assert idx == 0

def test_perpendicular_offset():
    # offset of 0.0072 lat is approx 800m
    route = Polyline([(28.5355, 77.3000), (28.5355, 77.4000)])
    dist, idx = route.distance_to(28.5355 + 0.0072, 77.3500)
    assert 790 <= dist <= 810
    assert idx == 0

def test_beyond_endpoint_clamps():
    route = Polyline([(28.5355, 77.3000), (28.5355, 77.4000)])
    # Dist to endpoint A
    dist1, idx1 = route.distance_to(28.5355, 77.29)
    assert idx1 == 0
    assert dist1 > 0
    
    # Dist to endpoint B
    dist2, idx2 = route.distance_to(28.5355, 77.41)
    assert idx2 == 0
    assert dist2 > 0

def test_zero_length_segment():
    route = Polyline([(28.0, 77.0), (28.0, 77.0), (28.0, 77.1)])
    dist, idx = route.distance_to(28.0, 77.05)
    assert idx == 1
    assert math.isclose(dist, 0.0, abs_tol=1e-5)

def test_nearest_segment_index():
    route = Polyline([(28.5355, 77.30), (28.5355, 77.35), (28.5355, 77.40), (28.5355, 77.45)])
    dist, idx = route.distance_to(28.5355, 77.375)
    assert idx == 1
    
    dist, idx = route.distance_to(28.5355, 77.425)
    assert idx == 2
