from __future__ import annotations

import hashlib
import random
from statistics import median
from typing import Iterable

from PIL import Image, ImageDraw
import numpy as np

from ppzm3.config import AppConfig
from ppzm3.types import Town, TownMasks, TownPlan


EDGE_BUFFER = 320
TOWN_SEPARATION = 260


def _rng_for_config(config: AppConfig) -> random.Random:
    seed = int(hashlib.sha256(f"{config.zip_code}-{config.map_name}".encode("utf-8")).hexdigest()[:16], 16)
    return random.Random(seed)


def _generate_town_specs(config: AppConfig) -> list[tuple[str, tuple[int, int], int]]:
    return (
        [("large", (46, 60), 92)] * config.large_towns
        + [("medium", (24, 32), 84)] * config.medium_towns
        + [("small", (10, 16), 76)] * config.small_towns
    )


def _neighbor_candidates(cell: tuple[int, int], primary_axis: str) -> list[tuple[tuple[int, int], int]]:
    x, y = cell
    if primary_axis == "h":
        return [((x + 1, y), 6), ((x - 1, y), 6), ((x, y + 1), 3), ((x, y - 1), 3)]
    return [((x + 1, y), 3), ((x - 1, y), 3), ((x, y + 1), 6), ((x, y - 1), 6)]


def _weighted_choice(rng: random.Random, items: list[tuple[tuple[int, int], int]]) -> tuple[int, int]:
    total = sum(weight for _, weight in items)
    pick = rng.randint(1, total)
    running = 0
    for value, weight in items:
        running += weight
        if pick <= running:
            return value
    return items[-1][0]


def _grow_block_cluster(rng: random.Random, target_blocks: int, primary_axis: str) -> set[tuple[int, int]]:
    occupied: set[tuple[int, int]] = {(0, 0)}
    frontier: set[tuple[int, int]] = {(0, 0)}

    while len(occupied) < target_blocks and frontier:
        anchor = rng.choice(tuple(frontier))
        weighted_neighbors = []
        for candidate, weight in _neighbor_candidates(anchor, primary_axis):
            if candidate in occupied:
                continue
            cx, cy = candidate
            distance_penalty = abs(cx) + abs(cy)
            weighted_neighbors.append((candidate, max(1, weight * 3 - distance_penalty)))
        if not weighted_neighbors:
            frontier.discard(anchor)
            continue
        chosen = _weighted_choice(rng, weighted_neighbors)
        occupied.add(chosen)
        frontier.add(chosen)
        if rng.random() < 0.35:
            frontier.discard(anchor)

    removable = []
    for cell in occupied:
        neighbors = sum((cell[0] + dx, cell[1] + dy) in occupied for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        if neighbors <= 1:
            removable.append(cell)
    rng.shuffle(removable)
    for cell in removable[: max(0, len(removable) // 5)]:
        if len(occupied) <= max(4, target_blocks - 4):
            break
        occupied.remove(cell)

    return occupied


def _normalize_cells(cells: Iterable[tuple[int, int]]) -> set[tuple[int, int]]:
    cells = set(cells)
    min_x = min(x for x, _ in cells)
    min_y = min(y for _, y in cells)
    return {(x - min_x, y - min_y) for x, y in cells}


def _segment_key(line: tuple[tuple[int, int], tuple[int, int]]) -> tuple[tuple[int, int], tuple[int, int]]:
    a, b = line
    return (a, b) if a <= b else (b, a)


def _append_unique(lines: list[tuple[tuple[int, int], tuple[int, int]]], line: tuple[tuple[int, int], tuple[int, int]], seen: set[tuple[tuple[int, int], tuple[int, int]]]) -> None:
    key = _segment_key(line)
    if key not in seen:
        seen.add(key)
        lines.append(key)


def _build_town_geometry(
    rng: random.Random,
    config: AppConfig,
    size: str,
    block_count_range: tuple[int, int],
    spacing: int,
) -> tuple[Town, set[tuple[int, int]], list[tuple[tuple[int, int], tuple[int, int]]], list[tuple[int, int, int, int]], tuple[int, int, int, int]]:
    target_blocks = rng.randint(*block_count_range)
    primary_axis = rng.choice(["h", "v"])
    cells = _normalize_cells(_grow_block_cluster(rng, target_blocks, primary_axis))

    max_x = max(x for x, _ in cells)
    max_y = max(y for _, y in cells)
    width = (max_x + 1) * spacing
    height = (max_y + 1) * spacing

    pad = 360
    origin_x = rng.randint(pad, max(pad, config.grid_width - width - pad))
    origin_y = rng.randint(pad, max(pad, config.grid_height - height - pad))

    local_roads_seen: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    local_roads: list[tuple[tuple[int, int], tuple[int, int]]] = []
    building_rects: list[tuple[int, int, int, int]] = []

    inset = max(10, spacing // 7)
    build_wiggle = max(4, spacing // 10)

    for gx, gy in cells:
        x0 = origin_x + gx * spacing
        y0 = origin_y + gy * spacing
        x1 = x0 + spacing
        y1 = y0 + spacing

        _append_unique(local_roads, ((x0, y0), (x1, y0)), local_roads_seen)
        _append_unique(local_roads, ((x0, y1), (x1, y1)), local_roads_seen)
        _append_unique(local_roads, ((x0, y0), (x0, y1)), local_roads_seen)
        _append_unique(local_roads, ((x1, y0), (x1, y1)), local_roads_seen)

        if size == "small" and rng.random() < 0.12:
            continue
        if size == "medium" and rng.random() < 0.08:
            continue
        if size == "large" and rng.random() < 0.05:
            continue

        bx0 = x0 + inset + rng.randint(0, build_wiggle)
        by0 = y0 + inset + rng.randint(0, build_wiggle)
        bx1 = x1 - inset - rng.randint(0, build_wiggle)
        by1 = y1 - inset - rng.randint(0, build_wiggle)
        if bx1 - bx0 > 16 and by1 - by0 > 16:
            building_rects.append((bx0, by0, bx1, by1))

    row_counts: dict[int, int] = {}
    col_counts: dict[int, int] = {}
    for gx, gy in cells:
        row_counts[gy] = row_counts.get(gy, 0) + 1
        col_counts[gx] = col_counts.get(gx, 0) + 1
    main_row = max(row_counts, key=row_counts.get)
    main_col = max(col_counts, key=col_counts.get)
    _append_unique(local_roads, ((origin_x, origin_y + main_row * spacing), (origin_x + width, origin_y + main_row * spacing)), local_roads_seen)
    _append_unique(local_roads, ((origin_x + main_col * spacing, origin_y), (origin_x + main_col * spacing, origin_y + height)), local_roads_seen)

    center_xy = (origin_x + width // 2, origin_y + height // 2)
    town = Town(
        name=f"{size.title()}Town",
        size=size,
        center_xy=center_xy,
        width=width,
        height=height,
        road_spacing=spacing,
        building_rows=0,
        building_cols=0,
    )
    bounds = (origin_x, origin_y, origin_x + width, origin_y + height)
    return town, cells, local_roads, building_rects, bounds


def _choose_backbone_positions(towns: list[Town], config: AppConfig) -> tuple[list[int], list[int]]:
    if not towns:
        return [config.grid_width // 2], [config.grid_height // 2]

    large = next((town for town in towns if town.size == "large"), None)
    if large is not None:
        base_x, base_y = large.center_xy
    else:
        base_x = int(median([town.center_xy[0] for town in towns]))
        base_y = int(median([town.center_xy[1] for town in towns]))

    xs = [max(EDGE_BUFFER, min(config.grid_width - EDGE_BUFFER, base_x))]
    ys = [max(EDGE_BUFFER, min(config.grid_height - EDGE_BUFFER, base_y))]

    width_third = config.grid_width // 3
    height_third = config.grid_height // 3

    far_x = [town.center_xy[0] for town in towns if abs(town.center_xy[0] - xs[0]) > width_third]
    far_y = [town.center_xy[1] for town in towns if abs(town.center_xy[1] - ys[0]) > height_third]

    if far_x:
        xs.append(max(EDGE_BUFFER, min(config.grid_width - EDGE_BUFFER, int(median(far_x)))))
    if far_y:
        ys.append(max(EDGE_BUFFER, min(config.grid_height - EDGE_BUFFER, int(median(far_y)))))

    xs = sorted(set(xs))
    ys = sorted(set(ys))

    if len(xs) == 2 and abs(xs[0] - xs[1]) < config.grid_width // 7:
        xs = xs[:1]
    if len(ys) == 2 and abs(ys[0] - ys[1]) < config.grid_height // 7:
        ys = ys[:1]

    return xs, ys


def _build_arterial_network(towns: list[Town], config: AppConfig) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    x_backbones, y_backbones = _choose_backbone_positions(towns, config)
    arterial_roads: list[tuple[tuple[int, int], tuple[int, int]]] = []
    seen: set[tuple[tuple[int, int], tuple[int, int]]] = set()

    for x in x_backbones:
        _append_unique(arterial_roads, ((x, 0), (x, config.grid_height)), seen)
    for y in y_backbones:
        _append_unique(arterial_roads, ((0, y), (config.grid_width, y)), seen)

    for town in towns:
        cx, cy = town.center_xy
        nearest_x = min(x_backbones, key=lambda x: abs(x - cx))
        nearest_y = min(y_backbones, key=lambda y: abs(y - cy))
        left = cx - town.width // 2
        right = cx + town.width // 2
        top = cy - town.height // 2
        bottom = cy + town.height // 2

        if abs(nearest_x - cx) <= abs(nearest_y - cy):
            edge_x = left if nearest_x < cx else right
            _append_unique(arterial_roads, ((nearest_x, cy), (edge_x, cy)), seen)
        else:
            edge_y = top if nearest_y < cy else bottom
            _append_unique(arterial_roads, ((cx, nearest_y), (cx, edge_y)), seen)

    return arterial_roads


def generate_towns(config: AppConfig) -> TownPlan:
    rng = _rng_for_config(config)
    towns: list[Town] = []
    occupied_bounds: list[tuple[int, int, int, int]] = []
    local_roads: list[tuple[tuple[int, int], tuple[int, int]]] = []
    building_rects: list[tuple[int, int, int, int]] = []

    specs = _generate_town_specs(config)
    for idx, (size, block_count_range, spacing) in enumerate(specs, start=1):
        for _ in range(500):
            town, _cells, town_roads, town_buildings, bounds = _build_town_geometry(rng, config, size, block_count_range, spacing)
            x0, y0, x1, y1 = bounds

            collision = False
            for ox0, oy0, ox1, oy1 in occupied_bounds:
                if not (x1 + TOWN_SEPARATION < ox0 or x0 - TOWN_SEPARATION > ox1 or y1 + TOWN_SEPARATION < oy0 or y0 - TOWN_SEPARATION > oy1):
                    collision = True
                    break
            if collision:
                continue

            town.name = f"{size.title()}Town{idx}"
            towns.append(town)
            occupied_bounds.append(bounds)
            building_rects.extend(town_buildings)
            local_roads.extend(town_roads)
            break

    arterial_roads = _build_arterial_network(towns, config)

    return TownPlan(
        towns=towns,
        arterial_roads=arterial_roads,
        local_roads=local_roads,
        building_rects=building_rects,
    )


def render_towns(base_image: Image.Image, plan: TownPlan, config: AppConfig):
    image = base_image.copy()
    draw = ImageDraw.Draw(image)

    roads_mask = Image.new("L", image.size, 0)
    roads_draw = ImageDraw.Draw(roads_mask)
    dirt_mask = Image.new("L", image.size, 0)
    dirt_draw = ImageDraw.Draw(dirt_mask)

    for line in plan.arterial_roads:
        draw.line(line, fill=config.palette["road_main"], width=16)
        roads_draw.line(line, fill=255, width=24)

    for line in plan.local_roads:
        draw.line(line, fill=config.palette["road_local"], width=8)
        roads_draw.line(line, fill=255, width=14)

    for rect in plan.building_rects:
        draw.rectangle(rect, fill=config.palette["dirt"])
        dirt_draw.rectangle(rect, fill=255)

    roads_np = np.array(roads_mask, dtype=np.uint8)
    dirt_np = np.array(dirt_mask, dtype=np.uint8)
    blocked = np.where((roads_np > 0) | (dirt_np > 0), 255, 0).astype(np.uint8)

    masks = TownMasks(
        roads_mask=roads_np,
        dirt_mask=dirt_np,
        blocked_mask=blocked,
    )
    return image, masks
