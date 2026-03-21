from collections import defaultdict
from typing import Any

from PIL import Image, ImageDraw

from ppzm3.config import AppConfig
from ppzm3.types import NormalizedLayers, RasterLayers


def _blank_grid(width: int, height: int) -> list[list[int]]:
    return [[0 for _ in range(width)] for _ in range(height)]


def _image_to_grid(image: Image.Image) -> list[list[int]]:
    width, height = image.size
    pixels = image.load()
    grid = _blank_grid(width, height)

    for y in range(height):
        for x in range(width):
            grid[y][x] = 1 if pixels[x, y] != 0 else 0

    return grid


def _latlon_to_global(lat: float, lon: float, config: AppConfig) -> tuple[int, int]:
    if config.bbox is None:
        raise RuntimeError("Config bbox is not set.")

    bbox = config.bbox
    lon_span = bbox.east - bbox.west
    lat_span = bbox.north - bbox.south

    if lon_span == 0 or lat_span == 0:
        return 0, 0

    x_ratio = (lon - bbox.west) / lon_span
    y_ratio = (bbox.north - lat) / lat_span

    x = int(round(x_ratio * (config.grid_width - 1)))
    y = int(round(y_ratio * (config.grid_height - 1)))

    x = max(0, min(config.grid_width - 1, x))
    y = max(0, min(config.grid_height - 1, y))
    return x, y


def _feature_bounds(points: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _is_closed(points: list[tuple[int, int]]) -> bool:
    return len(points) >= 3 and points[0] == points[-1]


def _intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)


def _new_mask(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    return image, draw


def _localize_points(points: list[tuple[int, int]], left: int, top: int) -> list[tuple[int, int]]:
    return [(x - left, y - top) for x, y in points]


def _index_features_by_cell(
    features: list[dict[str, Any]],
    cell_size: int,
) -> dict[tuple[int, int], list[int]]:
    index: dict[tuple[int, int], list[int]] = defaultdict(list)

    for i, feature in enumerate(features):
        min_x, min_y, max_x, max_y = feature["bounds"]
        cell_min_x = min_x // cell_size
        cell_max_x = max_x // cell_size
        cell_min_y = min_y // cell_size
        cell_max_y = max_y // cell_size

        for cy in range(cell_min_y, cell_max_y + 1):
            for cx in range(cell_min_x, cell_max_x + 1):
                index[(cx, cy)].append(i)

    return index


def prepare_render_data(normalized: NormalizedLayers, config: AppConfig) -> dict[str, Any]:
    def convert_features(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in items:
            pts = [_latlon_to_global(lat, lon, config) for lat, lon in item["coords"]]
            if len(pts) < 2:
                continue

            out.append(
                {
                    "kind": item["kind"],
                    "points": pts,
                    "bounds": _feature_bounds(pts),
                    "tags": item.get("tags", {}),
                }
            )
        return out

    roads = convert_features(normalized.roads)
    water = convert_features(normalized.water)
    landuse = convert_features(normalized.landuse)
    buildings = convert_features(normalized.buildings)

    cell_size = config.tiles_per_cell

    return {
        "roads": roads,
        "water": water,
        "landuse": landuse,
        "buildings": buildings,
        "indexes": {
            "roads": _index_features_by_cell(roads, cell_size),
            "water": _index_features_by_cell(water, cell_size),
            "landuse": _index_features_by_cell(landuse, cell_size),
            "buildings": _index_features_by_cell(buildings, cell_size),
        },
    }


def _candidate_feature_indices(
    prepared: dict[str, Any],
    layer_name: str,
    cell_x: int,
    cell_y: int,
) -> list[int]:
    index = prepared["indexes"][layer_name]
    found: set[int] = set()

    for yy in range(cell_y - 1, cell_y + 2):
        for xx in range(cell_x - 1, cell_x + 2):
            for idx in index.get((xx, yy), []):
                found.add(idx)

    return list(found)


def render_chunk_layers(
    prepared: dict[str, Any],
    config: AppConfig,
    cell_x: int,
    cell_y: int,
) -> RasterLayers:
    cell_size = config.tiles_per_cell
    pad = config.chunk_padding_tiles

    global_left = cell_x * cell_size - pad
    global_top = cell_y * cell_size - pad
    local_size = cell_size + (pad * 2)

    chunk_bounds = (
        global_left,
        global_top,
        global_left + local_size - 1,
        global_top + local_size - 1,
    )

    road_img, road_draw = _new_mask(local_size, local_size)
    water_img, water_draw = _new_mask(local_size, local_size)
    forest_img, forest_draw = _new_mask(local_size, local_size)
    farmland_img, farmland_draw = _new_mask(local_size, local_size)
    building_img, building_draw = _new_mask(local_size, local_size)
    residential_img, residential_draw = _new_mask(local_size, local_size)
    golf_img, golf_draw = _new_mask(local_size, local_size)

    for idx in _candidate_feature_indices(prepared, "roads", cell_x, cell_y):
        item = prepared["roads"][idx]
        if not _intersects(item["bounds"], chunk_bounds):
            continue
        pts = _localize_points(item["points"], global_left, global_top)
        width = config.road_widths.get(item["kind"], 2)
        road_draw.line(pts, fill=255, width=width, joint="curve")

    for idx in _candidate_feature_indices(prepared, "water", cell_x, cell_y):
        item = prepared["water"][idx]
        if not _intersects(item["bounds"], chunk_bounds):
            continue
        pts = _localize_points(item["points"], global_left, global_top)
        if _is_closed(item["points"]):
            water_draw.polygon(pts, fill=255, outline=255)
        else:
            water_draw.line(pts, fill=255, width=4, joint="curve")

    for idx in _candidate_feature_indices(prepared, "landuse", cell_x, cell_y):
        item = prepared["landuse"][idx]
        if not _intersects(item["bounds"], chunk_bounds):
            continue

        pts = _localize_points(item["points"], global_left, global_top)
        if len(pts) < 3:
            continue

        kind = item["kind"]

        if kind in {"forest", "wood"}:
            forest_draw.polygon(pts, fill=255, outline=255)
        elif kind in {"farmland", "farmyard", "meadow", "grass"}:
            farmland_draw.polygon(pts, fill=255, outline=255)
        elif kind in {"residential", "village_green", "park"}:
            residential_draw.polygon(pts, fill=255, outline=255)
        elif kind == "golf":
            golf_draw.polygon(pts, fill=255, outline=255)

    for idx in _candidate_feature_indices(prepared, "buildings", cell_x, cell_y):
        item = prepared["buildings"][idx]
        if not _intersects(item["bounds"], chunk_bounds):
            continue

        pts = _localize_points(item["points"], global_left, global_top)
        if len(pts) < 3:
            continue
        building_draw.polygon(pts, fill=255, outline=255)

    return RasterLayers(
        road=_image_to_grid(road_img),
        water=_image_to_grid(water_img),
        forest=_image_to_grid(forest_img),
        farmland=_image_to_grid(farmland_img),
        building=_image_to_grid(building_img),
        residential=_image_to_grid(residential_img),
        golf=_image_to_grid(golf_img),
    )


def _crop_grid(grid: list[list[int]], pad: int, cell_size: int) -> list[list[int]]:
    return [row[pad:pad + cell_size] for row in grid[pad:pad + cell_size]]


def crop_center_layers(layers: RasterLayers, pad: int, cell_size: int) -> RasterLayers:
    return RasterLayers(
        road=_crop_grid(layers.road, pad, cell_size),
        water=_crop_grid(layers.water, pad, cell_size),
        forest=_crop_grid(layers.forest, pad, cell_size),
        farmland=_crop_grid(layers.farmland, pad, cell_size),
        building=_crop_grid(layers.building, pad, cell_size),
        residential=_crop_grid(layers.residential, pad, cell_size),
        golf=_crop_grid(layers.golf, pad, cell_size),
    )