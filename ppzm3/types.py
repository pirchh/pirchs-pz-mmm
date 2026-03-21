from dataclasses import dataclass
from typing import Any, TypeAlias


PZColor: TypeAlias = tuple[int, int, int]


@dataclass(frozen=True)
class BBox:
    south: float
    west: float
    north: float
    east: float

    def as_overpass_tuple(self) -> tuple[float, float, float, float]:
        return (self.south, self.west, self.north, self.east)


@dataclass
class NormalizedLayers:
    roads: list[dict[str, Any]]
    water: list[dict[str, Any]]
    landuse: list[dict[str, Any]]
    buildings: list[dict[str, Any]]


@dataclass
class RasterLayers:
    road: list[list[int]]
    water: list[list[int]]
    forest: list[list[int]]
    farmland: list[list[int]]
    building: list[list[int]]
    residential: list[list[int]]
    golf: list[list[int]]