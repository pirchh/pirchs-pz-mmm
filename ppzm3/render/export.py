from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from ppzm3.config import AppConfig
from ppzm3.types import GolfMasks, NatureMasks, Placement, TownMasks, TownPlan


def ensure_dirs(config: AppConfig) -> None:
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "chunks").mkdir(parents=True, exist_ok=True)
    (config.output_dir / "debug").mkdir(parents=True, exist_ok=True)


def _save_mask(arr: np.ndarray, path: Path) -> None:
    Image.fromarray(arr.astype(np.uint8), mode="L").save(path)


def _save_chunk_pairs(map_image: Image.Image, veg_image: Image.Image, chunks_dir: Path, config: AppConfig) -> None:
    tilesize = config.tiles_per_cell
    for cy in range(config.cells_y):
        row_dir = chunks_dir / f"{cy:02d}"
        row_dir.mkdir(parents=True, exist_ok=True)
        for cx in range(config.cells_x):
            left = cx * tilesize
            top = cy * tilesize
            right = left + tilesize
            bottom = top + tilesize
            map_tile = map_image.crop((left, top, right, bottom))
            veg_tile = veg_image.crop((left, top, right, bottom))
            stem = f"{cx:02d}_{cy:02d}"
            map_tile.save(row_dir / f"{stem}.png")
            veg_tile.save(row_dir / f"{stem}_veg.png")


def export_run_artifacts(
    final_overview: Image.Image,
    veg_overview: Image.Image,
    nature_masks: NatureMasks,
    town_masks: TownMasks,
    golf_overlay: Image.Image,
    golf_masks: GolfMasks,
    town_plan: TownPlan,
    placement: Placement,
    config: AppConfig,
) -> None:
    overview_path = config.output_dir / "MAP.png"
    veg_path = config.output_dir / "MAP_veg.png"
    final_overview.save(overview_path)
    veg_overview.save(veg_path)

    golf_overlay.save(config.output_dir / "debug" / "golf_overlay.png")
    _save_mask(nature_masks.forest_dense_mask, config.output_dir / "debug" / "forest_dense_mask.png")
    _save_mask(nature_masks.water_mask, config.output_dir / "debug" / "nature_water_mask.png")
    _save_mask(nature_masks.medium_grass_mask, config.output_dir / "debug" / "medium_grass_mask.png")
    _save_mask(nature_masks.light_grass_mask, config.output_dir / "debug" / "light_grass_mask.png")
    _save_mask(town_masks.roads_mask, config.output_dir / "debug" / "roads_mask.png")
    _save_mask(town_masks.dirt_mask, config.output_dir / "debug" / "dirt_mask.png")
    _save_mask(golf_masks.footprint_mask, config.output_dir / "debug" / "golf_footprint_mask.png")

    metadata = {
        "map_name": config.map_name,
        "zip_code": config.zip_code,
        "cells_x": config.cells_x,
        "cells_y": config.cells_y,
        "tiles_per_cell": config.tiles_per_cell,
        "golf_course_name": config.golf_course_name,
        "golf_placement": {"x": placement.x, "y": placement.y, "score": placement.score},
        "outputs": {
            "map": "MAP.png",
            "veg": "MAP_veg.png",
            "chunk_rows": {
                "map": "chunks/<row>/<cx>_<cy>.png",
                "veg": "chunks/<row>/<cx>_<cy>_veg.png",
            },
        },
        "towns": [
            {
                "name": town.name,
                "size": town.size,
                "center_xy": list(town.center_xy),
                "width": town.width,
                "height": town.height,
                "road_spacing": town.road_spacing,
            }
            for town in town_plan.towns
        ],
    }
    (config.output_dir / "build_manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    _save_chunk_pairs(final_overview, veg_overview, config.output_dir / "chunks", config)
