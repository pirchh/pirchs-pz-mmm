from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ppzm3.types import BBox


@dataclass
class AppConfig:
    map_name: str
    zip_code: str
    country_code: str
    cells_x: int
    cells_y: int
    tiles_per_cell: int
    meters_per_tile: float

    center_lat: float | None
    center_lon: float | None
    bbox: BBox | None

    cache_dir: Path
    output_dir: Path

    overpass_url: str
    nominatim_url: str
    user_agent: str

    large_towns: int
    medium_towns: int
    small_towns: int

    golf_course_name: str
    golf_search_radius_m: int
    golf_padding_tiles: int
    golf_bbox_expand_m: int

    palette: dict[str, tuple[int, int, int]] = field(default_factory=dict)

    @property
    def grid_width(self) -> int:
        return self.cells_x * self.tiles_per_cell

    @property
    def grid_height(self) -> int:
        return self.cells_y * self.tiles_per_cell

    @staticmethod
    def default() -> "AppConfig":
        return AppConfig(
            map_name="ppzm3_region_20x20",
            zip_code="19380",
            country_code="us",
            cells_x=20,
            cells_y=20,
            tiles_per_cell=300,
            meters_per_tile=1.0,
            center_lat=None,
            center_lon=None,
            bbox=None,
            cache_dir=Path("cache"),
            output_dir=Path("output"),
            overpass_url="https://overpass-api.de/api/interpreter",
            nominatim_url="https://nominatim.openstreetmap.org/search",
            user_agent="ppzm3/1.1 orthogonal-world-builder",
            large_towns=1,
            medium_towns=1,
            small_towns=4,
            golf_course_name="Waynesborough Country Club",
            golf_search_radius_m=30000,
            golf_padding_tiles=12,
            golf_bbox_expand_m=150,
            palette={
                # WorldEd-recognized MAP.png colors
                "dark_grass": (90, 100, 35),
                "medium_grass": (117, 117, 47),
                "light_grass": (145, 135, 60),
                "sand": (210, 200, 160),
                "light_asphalt": (165, 160, 140),
                "dark_asphalt": (100, 100, 100),
                "medium_asphalt": (120, 120, 120),
                "gravel_dirt": (140, 70, 15),
                "dirt": (120, 70, 20),
                "dirt_grass": (80, 55, 20),
                "dark_pothole": (110, 100, 100),
                "light_pothole": (130, 120, 120),
                "water": (0, 138, 255),
                # Aliases for terrain/golf rendering
                "forest": (90, 100, 35),
                "road_main": (100, 100, 100),
                "road_local": (120, 120, 120),
                "golf_fairway": (145, 135, 60),
                "golf_green": (117, 117, 47),
                "golf_tee": (145, 135, 60),
                "golf_sand": (210, 200, 160),
                "golf_path": (80, 55, 20),
                "golf_rough": (117, 117, 47),
                # WorldEd-recognized MAP_veg.png colors
                "veg_bg": (0, 0, 0),
                "veg_dense_forest": (255, 0, 0),
                "veg_dense_trees_grass": (200, 0, 0),
                "veg_trees_grass": (127, 0, 0),
                "veg_fir_trees_grass": (64, 0, 0),
                "veg_grass_some_trees": (0, 128, 0),
                "veg_light_long_grass": (0, 255, 0),
                "veg_bushes_grass_few_trees": (255, 0, 255),
                "veg_dead_corn_1": (255, 128, 0),
                "veg_dead_corn_2": (220, 100, 0),
            },
        )
