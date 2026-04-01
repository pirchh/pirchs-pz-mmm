import logging
import time

import numpy as np

from ppzm3.config import AppConfig
from ppzm3.fetch.geocode import build_bbox_from_center, geocode_zip_center
from ppzm3.fetch.osm import fetch_golf_course_data, fetch_nature_data
from ppzm3.core.nature import enrich_veg_overview, normalize_nature_data, render_nature_overview, render_veg_overview
from ppzm3.core.towns import generate_towns, render_towns
from ppzm3.core.golf import normalize_golf_data, render_golf_overlay
from ppzm3.core.placement import find_best_golf_placement, paste_golf_overlay
from ppzm3.render.export import ensure_dirs, export_run_artifacts


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _log_step(log: logging.Logger, label: str, start: float) -> float:
    now = time.perf_counter()
    log.info("%s complete in %.1f sec", label, now - start)
    return now


def main() -> None:
    setup_logging()
    log = logging.getLogger("ppzm3")
    t0 = time.perf_counter()

    config = AppConfig.default()
    ensure_dirs(config)

    center_lat, center_lon = geocode_zip_center(config)
    config.center_lat = center_lat
    config.center_lon = center_lon
    config.bbox = build_bbox_from_center(
        center_lat=center_lat,
        center_lon=center_lon,
        cells_x=config.cells_x,
        cells_y=config.cells_y,
        tiles_per_cell=config.tiles_per_cell,
        meters_per_tile=config.meters_per_tile,
    )

    log.info("== ppzm3 Orthogonal World Builder ==")
    log.info("Map name: %s", config.map_name)
    log.info("ZIP: %s", config.zip_code)
    log.info("Cells: %s x %s", config.cells_x, config.cells_y)
    log.info("Tiles per cell: %s", config.tiles_per_cell)
    log.info("Grid: %s x %s", config.grid_width, config.grid_height)
    log.info("Center: (%.6f, %.6f)", config.center_lat, config.center_lon)
    log.info("BBox: %s", config.bbox)

    step_t = time.perf_counter()
    log.info("Step 1/9: fetching nature data...")
    raw_nature = fetch_nature_data(config)
    step_t = _log_step(log, "Step 1/9 fetch nature data", step_t)

    log.info("Step 2/9: normalizing nature data...")
    normalized_nature = normalize_nature_data(raw_nature, config)
    step_t = _log_step(log, "Step 2/9 normalize nature data", step_t)

    log.info("Step 3/9: rendering terrain overview...")
    base_overview, masks = render_nature_overview(normalized_nature, config)
    step_t = _log_step(log, "Step 3/9 render terrain overview", step_t)

    log.info("Step 4/9: rendering initial vegetation overview...")
    veg_overview = render_veg_overview(normalized_nature, masks, config)
    step_t = _log_step(log, "Step 4/9 render initial vegetation overview", step_t)

    log.info("Step 5/9: generating and rendering towns...")
    town_plan = generate_towns(config)
    town_overview, town_masks = render_towns(base_overview.copy(), town_plan, config)
    step_t = _log_step(log, "Step 5/9 generate and render towns", step_t)

    log.info("Step 6/9: fetching and rendering golf course...")
    raw_golf = fetch_golf_course_data(config)
    golf_geometry = normalize_golf_data(raw_golf, config)
    golf_overlay, golf_masks = render_golf_overlay(golf_geometry, config)
    step_t = _log_step(log, "Step 6/9 fetch and render golf course", step_t)

    blocked_mask = np.where(
        (town_masks.blocked_mask > 0)
        | (masks.water_mask > 0)
        | (masks.light_grass_mask > 0),
        255,
        0,
    ).astype(np.uint8)

    log.info("Step 7/9: finding golf placement...")
    placement = find_best_golf_placement(
        forest_mask=masks.forest_dense_mask,
        blocked_mask=blocked_mask,
        golf_mask=golf_masks.footprint_mask,
        config=config,
    )
    step_t = _log_step(log, "Step 7/9 golf placement", step_t)

    log.info("Step 8/9: compositing golf and enriching vegetation...")
    final_overview = paste_golf_overlay(
        town_overview,
        golf_overlay=golf_overlay,
        golf_footprint=golf_masks.footprint_mask,
        placement=placement,
    )

    placed_golf_mask = np.zeros((config.grid_height, config.grid_width), dtype=np.uint8)
    gh, gw = golf_masks.footprint_mask.shape
    placed_golf_mask[placement.y:placement.y + gh, placement.x:placement.x + gw] = golf_masks.footprint_mask
    veg_overview = enrich_veg_overview(
        veg_image=veg_overview,
        nature_masks=masks,
        town_masks=town_masks,
        placed_golf_mask=placed_golf_mask,
        config=config,
    )
    step_t = _log_step(log, "Step 8/9 composite golf and enrich vegetation", step_t)

    log.info("Step 9/9: exporting map, veg, chunks, and debug artifacts...")
    export_run_artifacts(
        final_overview=final_overview,
        veg_overview=veg_overview,
        nature_masks=masks,
        town_masks=town_masks,
        golf_overlay=golf_overlay,
        golf_masks=golf_masks,
        town_plan=town_plan,
        placement=placement,
        config=config,
    )

    step_t = _log_step(log, "Step 9/9 export artifacts", step_t)

    elapsed = time.perf_counter() - t0
    log.info("Done. Output: %s", config.output_dir.resolve())
    log.info("Elapsed: %.1f sec", elapsed)


if __name__ == "__main__":
    main()
