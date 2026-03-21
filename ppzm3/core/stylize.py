from ppzm3.config import AppConfig
from ppzm3.types import RasterLayers


def _clone(grid: list[list[int]]) -> list[list[int]]:
    return [row[:] for row in grid]


def _dilate(grid: list[list[int]], radius: int = 1) -> list[list[int]]:
    h = len(grid)
    w = len(grid[0]) if h else 0
    out = _clone(grid)

    for y in range(h):
        for x in range(w):
            if grid[y][x] != 1:
                continue

            for yy in range(max(0, y - radius), min(h, y + radius + 1)):
                for xx in range(max(0, x - radius), min(w, x + radius + 1)):
                    out[yy][xx] = 1

    return out


def _erode(grid: list[list[int]], radius: int = 1) -> list[list[int]]:
    h = len(grid)
    w = len(grid[0]) if h else 0
    out = _clone(grid)

    for y in range(h):
        for x in range(w):
            if grid[y][x] == 0:
                continue

            keep = True
            for yy in range(max(0, y - radius), min(h, y + radius + 1)):
                for xx in range(max(0, x - radius), min(w, x + radius + 1)):
                    if grid[yy][xx] == 0:
                        keep = False
                        break
                if not keep:
                    break

            out[y][x] = 1 if keep else 0

    return out


def _open(grid: list[list[int]], radius: int = 1) -> list[list[int]]:
    return _dilate(_erode(grid, radius), radius)


def _close(grid: list[list[int]], radius: int = 1) -> list[list[int]]:
    return _erode(_dilate(grid, radius), radius)


def _subtract(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
    h = len(a)
    w = len(a[0]) if h else 0
    out = _clone(a)

    for y in range(h):
        for x in range(w):
            if b[y][x] == 1:
                out[y][x] = 0

    return out


def _and(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
    h = len(a)
    w = len(a[0]) if h else 0
    out = _clone(a)

    for y in range(h):
        for x in range(w):
            out[y][x] = 1 if a[y][x] == 1 and b[y][x] == 1 else 0

    return out


def _or(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
    h = len(a)
    w = len(a[0]) if h else 0
    out = _clone(a)

    for y in range(h):
        for x in range(w):
            out[y][x] = 1 if a[y][x] == 1 or b[y][x] == 1 else 0

    return out


def _count_neighbors(grid: list[list[int]], x: int, y: int, radius: int = 1) -> int:
    h = len(grid)
    w = len(grid[0]) if h else 0
    count = 0

    for yy in range(max(0, y - radius), min(h, y + radius + 1)):
        for xx in range(max(0, x - radius), min(w, x + radius + 1)):
            if xx == x and yy == y:
                continue
            if grid[yy][xx] == 1:
                count += 1

    return count


def _remove_isolated_pixels(grid: list[list[int]], min_neighbors: int = 2) -> list[list[int]]:
    h = len(grid)
    w = len(grid[0]) if h else 0
    out = _clone(grid)

    for y in range(h):
        for x in range(w):
            if grid[y][x] == 0:
                continue

            n = _count_neighbors(grid, x, y, radius=1)
            if n < min_neighbors:
                out[y][x] = 0

    return out


def _remove_small_components(grid: list[list[int]], min_size: int = 8) -> list[list[int]]:
    h = len(grid)
    w = len(grid[0]) if h else 0
    out = _clone(grid)
    visited = [[False for _ in range(w)] for _ in range(h)]

    for y in range(h):
        for x in range(w):
            if visited[y][x] or grid[y][x] == 0:
                continue

            stack = [(x, y)]
            component: list[tuple[int, int]] = []
            visited[y][x] = True

            while stack:
                cx, cy = stack.pop()
                component.append((cx, cy))

                for ny in range(max(0, cy - 1), min(h, cy + 2)):
                    for nx in range(max(0, cx - 1), min(w, cx + 2)):
                        if visited[ny][nx]:
                            continue
                        if grid[ny][nx] != 1:
                            continue
                        visited[ny][nx] = True
                        stack.append((nx, ny))

            if len(component) < min_size:
                for cx, cy in component:
                    out[cy][cx] = 0

    return out


def _remove_buildings_on_water(building: list[list[int]], water: list[list[int]]) -> list[list[int]]:
    return _subtract(building, water)


def _remove_roads_on_water_except_bridges(
    road: list[list[int]],
    water: list[list[int]],
) -> list[list[int]]:
    h = len(road)
    w = len(road[0]) if h else 0
    out = _clone(road)

    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if road[y][x] == 1 and water[y][x] == 1:
                neighbors = _count_neighbors(road, x, y, radius=1)
                if neighbors < 5:
                    out[y][x] = 0

    return out


def _carve_roads_out_of_buildings(
    road: list[list[int]],
    building: list[list[int]],
) -> list[list[int]]:
    building_buffer = _dilate(building, radius=1)
    out = _subtract(road, building_buffer)
    out = _close(out, radius=1)
    out = _remove_small_components(out, min_size=6)
    return out


def _inflate_residential_from_buildings(
    building: list[list[int]],
    road: list[list[int]],
    existing_residential: list[list[int]],
) -> list[list[int]]:
    near_road = _dilate(road, radius=6)
    building_lots = _dilate(building, radius=4)
    candidate = _and(building_lots, near_road)

    merged = _or(existing_residential, candidate)
    merged = _close(merged, radius=2)
    merged = _open(merged, radius=1)
    merged = _remove_small_components(merged, min_size=20)
    return merged


def _tame_farmland(
    farmland: list[list[int]],
    road: list[list[int]],
    water: list[list[int]],
    residential: list[list[int]],
    golf: list[list[int]],
) -> list[list[int]]:
    out = _erode(farmland, radius=2)
    out = _open(out, radius=2)

    road_buffer = _dilate(road, radius=4)
    water_buffer = _dilate(water, radius=2)
    residential_buffer = _dilate(residential, radius=2)

    out = _subtract(out, road_buffer)
    out = _subtract(out, water_buffer)
    out = _subtract(out, residential_buffer)
    out = _subtract(out, golf)

    out = _close(out, radius=1)
    out = _remove_small_components(out, min_size=30)
    return out


def _tame_forest(
    forest: list[list[int]],
    road: list[list[int]],
    water: list[list[int]],
    residential: list[list[int]],
    golf: list[list[int]],
) -> list[list[int]]:
    out = _close(forest, radius=2)
    out = _open(out, radius=1)

    road_buffer = _dilate(road, radius=3)
    water_buffer = _dilate(water, radius=1)
    residential_buffer = _dilate(residential, radius=2)

    out = _subtract(out, road_buffer)
    out = _subtract(out, water_buffer)
    out = _subtract(out, residential_buffer)
    out = _subtract(out, golf)

    out = _close(out, radius=1)
    out = _remove_small_components(out, min_size=20)
    return out


def stylize_grid(raster: RasterLayers, config: AppConfig) -> RasterLayers:
    road = _close(raster.road, radius=1)
    road = _remove_small_components(road, min_size=6)

    water = _close(raster.water, radius=1)

    building = _close(raster.building, radius=1)
    building = _remove_small_components(building, min_size=10)
    building = _remove_isolated_pixels(building, min_neighbors=1)
    building = _remove_buildings_on_water(building, water)
    building = _subtract(building, raster.golf)

    golf = _close(raster.golf, radius=1)
    golf = _remove_small_components(golf, min_size=20)
    golf = _subtract(golf, water)
    golf = _subtract(golf, building)

    road = _remove_roads_on_water_except_bridges(road, water)
    road = _carve_roads_out_of_buildings(road, building)

    residential = _inflate_residential_from_buildings(
        building=building,
        road=road,
        existing_residential=raster.residential,
    )
    residential = _subtract(residential, water)
    residential = _subtract(residential, golf)

    farmland = _tame_farmland(raster.farmland, road, water, residential, golf)
    forest = _tame_forest(raster.forest, road, water, residential, golf)

    residential = _subtract(residential, building)
    farmland = _subtract(farmland, building)
    forest = _subtract(forest, building)

    farmland = _subtract(farmland, residential)
    forest = _subtract(forest, residential)

    residential = _remove_small_components(residential, min_size=20)
    farmland = _remove_small_components(farmland, min_size=30)
    forest = _remove_small_components(forest, min_size=20)

    return RasterLayers(
        road=road,
        water=water,
        forest=forest,
        farmland=farmland,
        building=building,
        residential=residential,
        golf=golf,
    )