from PIL import Image

from ppzm3.config import AppConfig
from ppzm3.types import NormalizedLayers, RasterLayers


def _save_mask(grid: list[list[int]], path: str) -> None:
    height = len(grid)
    width = len(grid[0]) if height else 0

    image = Image.new("RGB", (width, height), (0, 0, 0))
    pixels = image.load()

    for y in range(height):
        for x in range(width):
            if grid[y][x]:
                pixels[x, y] = (255, 255, 255)

    image.save(path)


def export_debug_layers(
    raw_osm: dict,
    normalized: NormalizedLayers,
    raster: RasterLayers,
    final_grid: RasterLayers,
    config: AppConfig,
) -> None:
    _save_mask(raster.road, str(config.output_dir / f"{config.map_name}_road_mask.png"))
    _save_mask(raster.water, str(config.output_dir / f"{config.map_name}_water_mask.png"))
    _save_mask(raster.forest, str(config.output_dir / f"{config.map_name}_forest_mask.png"))
    _save_mask(raster.farmland, str(config.output_dir / f"{config.map_name}_farmland_mask.png"))
    _save_mask(raster.building, str(config.output_dir / f"{config.map_name}_building_mask.png"))
    _save_mask(raster.residential, str(config.output_dir / f"{config.map_name}_residential_mask.png"))
    _save_mask(raster.golf, str(config.output_dir / f"{config.map_name}_golf_mask.png"))