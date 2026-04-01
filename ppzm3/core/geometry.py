from __future__ import annotations

import math
from typing import Iterable

from ppzm3.types import BBox


def latlon_to_global_xy(lat: float, lon: float, bbox: BBox, width: int, height: int) -> tuple[int, int]:
    x_ratio = (lon - bbox.west) / (bbox.east - bbox.west)
    y_ratio = (bbox.north - lat) / (bbox.north - bbox.south)
    x = int(round(x_ratio * (width - 1)))
    y = int(round(y_ratio * (height - 1)))
    return x, y


def normalize_points(points: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(float(lat), float(lon)) for lat, lon in points]


def bbox_from_points(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return min(lats), min(lons), max(lats), max(lons)


def meters_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2.0))
    y = math.radians(lat2 - lat1)
    return 6_371_000.0 * math.sqrt(x * x + y * y)
