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

    center_lat: float | None
    center_lon: float | None
    bbox: BBox | None

    cache_dir: Path
    output_dir: Path

    overpass_url: str
    nominatim_url: str
    user_agent: str

    road_widths: dict[str, int] = field(default_factory=dict)

    chunk_padding_tiles: int = 24
    overview_block_cells: int = 10
    log_every_n_chunks: int = 25
    write_debug_masks: bool = False

    @property
    def grid_width(self) -> int:
        return self.cells_x * self.tiles_per_cell

    @property
    def grid_height(self) -> int:
        return self.cells_y * self.tiles_per_cell

    @staticmethod
    def default() -> "AppConfig":
        return AppConfig(
            map_name="ppzm3_19010_50x40",
            zip_code="19010",
            country_code="us",
            cells_x=50,
            cells_y=40,
            tiles_per_cell=300,
            center_lat=None,
            center_lon=None,
            bbox=None,
            cache_dir=Path("cache"),
            output_dir=Path("output"),
            overpass_url="https://overpass.kumi.systems/api/interpreter",
            nominatim_url="https://nominatim.openstreetmap.org/search",
            user_agent="ppzm3/0.5 (Project Zomboid chunked renderer)",
            road_widths={
                "motorway": 14,
                "trunk": 12,
                "primary": 10,
                "secondary": 8,
                "tertiary": 6,
                "residential": 4,
                "service": 3,
                "track": 2,
                "unclassified": 4,
            },
            chunk_padding_tiles=24,
            overview_block_cells=20,
            log_every_n_chunks=25,
            write_debug_masks=False,
        )