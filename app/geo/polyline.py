import math
from typing import Sequence, Tuple

EARTH_R = 6371008.8

def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_R * c

class Polyline:
    def __init__(self, points: Sequence[Tuple[float, float]]):
        """points = [(lat,lng),...], len>=2 else ValueError."""
        if not points or len(points) < 2:
            raise ValueError("Polyline must have at least 2 points")
        self.points = points
        
        # Calculate centroid latitude for planar projection
        self.lat0 = sum(p[0] for p in points) / len(points)
        self.lng0 = points[0][1] # Reference longitude
        
        self.local_points = [self._project(lat, lng) for lat, lng in points]
        
    def _project(self, lat: float, lng: float) -> Tuple[float, float]:
        """Projects once to local planar metres (equirectangular) around the centroid latitude:
          x = radians(lng - lng0) * cos(radians(lat0)) * R
          y = radians(lat - lat0) * R
        """
        x = math.radians(lng - self.lng0) * math.cos(math.radians(self.lat0)) * EARTH_R
        y = math.radians(lat - self.lat0) * EARTH_R
        return (x, y)

    def distance_to(self, lat: float, lng: float) -> Tuple[float, int]:
        """returns (min distance in metres, index of nearest segment). O(S)."""
        px, py = self._project(lat, lng)
        
        min_dist = float('inf')
        min_idx = -1
        
        for i in range(len(self.local_points) - 1):
            ax, ay = self.local_points[i]
            bx, by = self.local_points[i + 1]
            
            # ab = B - A
            ab_x = bx - ax
            ab_y = by - ay
            
            # ap = P - A
            ap_x = px - ax
            ap_y = py - ay
            
            denom = ab_x * ab_x + ab_y * ab_y
            
            if denom == 0:
                t = 0
            else:
                dot = ap_x * ab_x + ap_y * ab_y
                t = max(0.0, min(1.0, dot / denom))
                
            closest_x = ax + t * ab_x
            closest_y = ay + t * ab_y
            
            dx = px - closest_x
            dy = py - closest_y
            dist = math.sqrt(dx * dx + dy * dy)
            
            if dist < min_dist:
                min_dist = dist
                min_idx = i
                
        return min_dist, min_idx

    @property
    def length_m(self) -> float:
        total = 0.0
        for i in range(len(self.points) - 1):
            total += haversine_m(
                self.points[i][0], self.points[i][1],
                self.points[i+1][0], self.points[i+1][1]
            )
        return total
