from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BBox:
    south: float
    west: float
    north: float
    east: float

    def as_overpass(self) -> str:
        return f"{self.south},{self.west},{self.north},{self.east}"


@dataclass
class Feature:
    tags: dict[str, str]
    geometry: list[tuple[float, float]]
    feature_type: str
    closed: bool = False


@dataclass
class MultiLayerNature:
    water_polygons: list[Feature] = field(default_factory=list)
    water_lines: list[Feature] = field(default_factory=list)
    forest_polygons: list[Feature] = field(default_factory=list)
    tree_lines: list[Feature] = field(default_factory=list)
    tree_points: list[Feature] = field(default_factory=list)
    medium_grass_polygons: list[Feature] = field(default_factory=list)
    light_grass_polygons: list[Feature] = field(default_factory=list)
    scrub_polygons: list[Feature] = field(default_factory=list)


@dataclass
class GolfLayers:
    course_polygons: list[Feature] = field(default_factory=list)
    fairways: list[Feature] = field(default_factory=list)
    greens: list[Feature] = field(default_factory=list)
    tees: list[Feature] = field(default_factory=list)
    sand: list[Feature] = field(default_factory=list)
    water: list[Feature] = field(default_factory=list)
    paths: list[Feature] = field(default_factory=list)
    woods: list[Feature] = field(default_factory=list)
    rough: list[Feature] = field(default_factory=list)


@dataclass
class Town:
    name: str
    size: str
    center_xy: tuple[int, int]
    width: int
    height: int
    road_spacing: int
    building_rows: int
    building_cols: int


@dataclass
class TownPlan:
    towns: list[Town]
    arterial_roads: list[tuple[tuple[int, int], tuple[int, int]]] = field(default_factory=list)
    local_roads: list[tuple[tuple[int, int], tuple[int, int]]] = field(default_factory=list)
    building_rects: list[tuple[int, int, int, int]] = field(default_factory=list)


@dataclass
class NatureMasks:
    forest_dense_mask: Any
    water_mask: Any
    medium_grass_mask: Any
    light_grass_mask: Any


@dataclass
class TownMasks:
    roads_mask: Any
    dirt_mask: Any
    blocked_mask: Any


@dataclass
class GolfMasks:
    footprint_mask: Any
    water_mask: Any


@dataclass
class Placement:
    x: int
    y: int
    score: int
