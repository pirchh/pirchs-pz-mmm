from __future__ import annotations

import logging

from PIL import Image, ImageDraw
import numpy as np

from ppzm3.config import AppConfig
from ppzm3.core.geometry import latlon_to_global_xy
from ppzm3.core.osm_parse import parse_features
from ppzm3.types import Feature, MultiLayerNature, NatureMasks, TownMasks

log = logging.getLogger("ppzm3.nature")


def normalize_nature_data(raw_osm: dict, config: AppConfig) -> MultiLayerNature:
    features = parse_features(raw_osm)
    layers = MultiLayerNature()

    for feat in features:
        tags = feat.tags
        natural = tags.get("natural")
        landuse = tags.get("landuse")
        leisure = tags.get("leisure")
        waterway = tags.get("waterway")

        if natural == "water":
            if feat.closed:
                layers.water_polygons.append(feat)
            else:
                layers.water_lines.append(feat)
        elif waterway:
            layers.water_lines.append(feat)
        elif landuse == "forest" or natural == "wood":
            layers.forest_polygons.append(feat)
        elif natural == "tree_row":
            layers.tree_lines.append(feat)
        elif natural == "tree":
            layers.tree_points.append(feat)
        elif natural == "scrub":
            layers.scrub_polygons.append(feat)
        elif landuse in {"meadow", "orchard", "farmland"} or natural == "grassland":
            layers.medium_grass_polygons.append(feat)
        elif landuse == "grass" or leisure in {"park", "pitch", "common"}:
            layers.light_grass_polygons.append(feat)

    return layers


def _feature_points(feat: Feature, config: AppConfig) -> list[tuple[int, int]]:
    return [
        latlon_to_global_xy(lat, lon, config.bbox, config.grid_width, config.grid_height)
        for lat, lon in feat.geometry
    ]


def _clamp_xy(x: int, y: int, width: int, height: int) -> tuple[int, int]:
    return max(0, min(width - 1, x)), max(0, min(height - 1, y))


def _ground_suffix(x: int, y: int, masks: NatureMasks) -> str:
    h, w = masks.medium_grass_mask.shape
    x, y = _clamp_xy(x, y, w, h)
    if masks.light_grass_mask[y, x] > 0:
        return "light"
    if masks.medium_grass_mask[y, x] > 0:
        return "medium"
    return "dark"


def render_nature_overview(layers: MultiLayerNature, config: AppConfig):
    image = Image.new("RGB", (config.grid_width, config.grid_height), config.palette["dark_grass"])
    draw = ImageDraw.Draw(image)

    forest_mask = Image.new("L", image.size, 0)
    forest_draw = ImageDraw.Draw(forest_mask)
    water_mask = Image.new("L", image.size, 0)
    water_draw = ImageDraw.Draw(water_mask)
    medium_grass_mask = Image.new("L", image.size, 0)
    medium_grass_draw = ImageDraw.Draw(medium_grass_mask)
    light_grass_mask = Image.new("L", image.size, 0)
    light_grass_draw = ImageDraw.Draw(light_grass_mask)

    for feat in layers.medium_grass_polygons:
        pts = _feature_points(feat, config)
        if len(pts) >= 3:
            draw.polygon(pts, fill=config.palette["medium_grass"])
            medium_grass_draw.polygon(pts, fill=255)

    for feat in layers.light_grass_polygons:
        pts = _feature_points(feat, config)
        if len(pts) >= 3:
            draw.polygon(pts, fill=config.palette["light_grass"])
            light_grass_draw.polygon(pts, fill=255)

    for feat in layers.scrub_polygons:
        pts = _feature_points(feat, config)
        if len(pts) >= 3:
            draw.polygon(pts, fill=config.palette["medium_grass"])
            forest_draw.polygon(pts, fill=128)

    for feat in layers.forest_polygons:
        pts = _feature_points(feat, config)
        if len(pts) >= 3:
            draw.polygon(pts, fill=config.palette["forest"])
            forest_draw.polygon(pts, fill=255)

    # Tree rows/points still contribute to vegetation density, but are not painted as bright red on MAP.png.
    for feat in layers.tree_lines:
        pts = _feature_points(feat, config)
        if len(pts) >= 2:
            forest_draw.line(pts, fill=220, width=6)

    for feat in layers.tree_points:
        pts = _feature_points(feat, config)
        if pts:
            x, y = pts[0]
            forest_draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=220)

    for feat in layers.water_polygons:
        pts = _feature_points(feat, config)
        if len(pts) >= 3:
            draw.polygon(pts, fill=config.palette["water"])
            water_draw.polygon(pts, fill=255)

    for feat in layers.water_lines:
        pts = _feature_points(feat, config)
        if len(pts) >= 2:
            draw.line(pts, fill=config.palette["water"], width=8)
            water_draw.line(pts, fill=255, width=10)

    masks = NatureMasks(
        forest_dense_mask=np.array(forest_mask, dtype=np.uint8),
        water_mask=np.array(water_mask, dtype=np.uint8),
        medium_grass_mask=np.array(medium_grass_mask, dtype=np.uint8),
        light_grass_mask=np.array(light_grass_mask, dtype=np.uint8),
    )
    return image, masks




def _neighbor_sum(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.astype(np.int32)

    src = mask.astype(np.int64, copy=False)
    padded = np.pad(src, radius, mode="edge")
    integral = padded.cumsum(axis=0, dtype=np.int64).cumsum(axis=1, dtype=np.int64)

    window = radius * 2 + 1
    br = integral[window - 1 :, window - 1 :]
    left = np.pad(integral[window - 1 :, :-window], ((0, 0), (1, 0)), mode="constant")
    top = np.pad(integral[:-window, window - 1 :], ((1, 0), (0, 0)), mode="constant")
    corner = np.pad(integral[:-window, :-window], ((1, 0), (1, 0)), mode="constant")
    return (br - left - top + corner).astype(np.int32)


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.copy()
    return (_neighbor_sum((mask > 0).astype(np.uint8), radius) > 0).astype(np.uint8) * 255


def enrich_veg_overview(
    veg_image: Image.Image,
    nature_masks: NatureMasks,
    town_masks: TownMasks,
    placed_golf_mask: np.ndarray,
    config: AppConfig,
) -> Image.Image:
    log.info("Veg enrichment: building source masks...")
    veg = np.array(veg_image, dtype=np.uint8)

    forest = (nature_masks.forest_dense_mask > 0).astype(np.uint8)
    medium = (nature_masks.medium_grass_mask > 0).astype(np.uint8)
    light = (nature_masks.light_grass_mask > 0).astype(np.uint8)
    roads = (town_masks.roads_mask > 0).astype(np.uint8)
    dirt = (town_masks.dirt_mask > 0).astype(np.uint8)
    water = (nature_masks.water_mask > 0).astype(np.uint8)
    golf = (placed_golf_mask > 0).astype(np.uint8)

    wilderness = 1 - np.clip(light + roads + dirt + water + golf, 0, 1)
    dark = (wilderness > 0).astype(np.uint8) * (1 - np.clip(medium + light, 0, 1))

    seed_strength = (
        (forest > 0).astype(np.int32) * 5
        + medium.astype(np.int32) * 2
        + dark.astype(np.int32) * 3
    )

    log.info("Veg enrichment: neighborhood density passes...")
    local_forest = _neighbor_sum(forest, 4)
    broad_forest = _neighbor_sum(forest, 10)
    local_dark = _neighbor_sum(dark.astype(np.uint8), 8)
    broad_dark = _neighbor_sum(dark.astype(np.uint8), 20)

    log.info("Veg enrichment: road distance bands...")
    road_band_0 = _dilate(roads * 255, 8) > 0
    road_band_1 = _dilate(roads * 255, 20) > 0
    road_band_2 = _dilate(roads * 255, 38) > 0
    road_band_3 = _dilate(roads * 255, 64) > 0

    log.info("Veg enrichment: town, water, and golf exclusion bands...")
    town_core = dirt > 0
    town_band_0 = _dilate(dirt * 255, 8) > 0
    town_band_1 = _dilate(dirt * 255, 18) > 0
    town_band_2 = _dilate(dirt * 255, 34) > 0

    water_core = water > 0
    water_band_0 = _dilate(water * 255, 4) > 0
    water_band_1 = _dilate(water * 255, 10) > 0

    golf_core = golf > 0
    golf_band = _dilate(golf * 255, 14) > 0

    blocked = town_core | water_core | golf_core
    no_dense = town_band_0 | water_band_0 | golf_band
    no_trees = town_band_1 | golf_band

    log.info("Veg enrichment: scoring vegetation density...")
    density_score = seed_strength.copy()
    density_score += (broad_dark // 90)
    density_score += (local_dark // 28)
    density_score += (broad_forest // 35)
    density_score += (local_forest // 10)

    density_score -= road_band_3.astype(np.int32) * 2
    density_score -= road_band_2.astype(np.int32) * 3
    density_score -= road_band_1.astype(np.int32) * 4
    density_score -= road_band_0.astype(np.int32) * 5

    density_score -= town_band_2.astype(np.int32) * 2
    density_score -= town_band_1.astype(np.int32) * 3
    density_score -= town_band_0.astype(np.int32) * 5

    density_score -= water_band_1.astype(np.int32) * 2
    density_score -= water_band_0.astype(np.int32) * 4

    density_score = np.where(wilderness > 0, density_score, -999)

    dense_forest = (density_score >= 8) & ~no_dense & ~blocked
    dense_trees = (density_score >= 5) & ~dense_forest & ~no_dense & ~blocked
    trees_grass = (density_score >= 2) & ~dense_forest & ~dense_trees & ~no_trees & ~blocked
    grass_some_trees = (
        ((density_score >= 0) & (wilderness > 0) & ~light.astype(bool))
        | ((medium > 0) & ~town_band_1 & ~water_band_0)
    ) & ~dense_forest & ~dense_trees & ~trees_grass & ~blocked
    light_long_grass = (
        ((wilderness > 0) & (density_score >= -2))
        | ((light > 0) & ~road_band_1 & ~town_band_0 & ~water_band_0 & ~golf_band)
    ) & ~dense_forest & ~dense_trees & ~trees_grass & ~grass_some_trees & ~blocked

    veg[:] = config.palette["veg_bg"]
    veg[light_long_grass] = config.palette["veg_light_long_grass"]
    veg[grass_some_trees] = config.palette["veg_grass_some_trees"]
    veg[trees_grass] = config.palette["veg_trees_grass"]
    veg[dense_trees] = config.palette["veg_dense_trees_grass"]
    veg[dense_forest] = config.palette["veg_dense_forest"]

    log.info(
        "Veg enrichment complete: dense_forest=%d dense_trees=%d trees_grass=%d grass_some_trees=%d light_long_grass=%d",
        int(dense_forest.sum()),
        int(dense_trees.sum()),
        int(trees_grass.sum()),
        int(grass_some_trees.sum()),
        int(light_long_grass.sum()),
    )

    return Image.fromarray(veg, mode="RGB")

def render_veg_overview(layers: MultiLayerNature, masks: NatureMasks, config: AppConfig) -> Image.Image:
    image = Image.new("RGB", (config.grid_width, config.grid_height), config.palette["veg_bg"])
    draw = ImageDraw.Draw(image)

    for feat in layers.scrub_polygons:
        pts = _feature_points(feat, config)
        if len(pts) >= 3:
            cx = sum(x for x, _ in pts) // len(pts)
            cy = sum(y for _, y in pts) // len(pts)
            suffix = _ground_suffix(cx, cy, masks)
            fill = (
                config.palette["veg_bushes_grass_few_trees"]
                if suffix in {"dark", "medium"}
                else config.palette["veg_light_long_grass"]
            )
            draw.polygon(pts, fill=fill)

    for feat in layers.forest_polygons:
        pts = _feature_points(feat, config)
        if len(pts) >= 3:
            cx = sum(x for x, _ in pts) // len(pts)
            cy = sum(y for _, y in pts) // len(pts)
            suffix = _ground_suffix(cx, cy, masks)
            fill = (
                config.palette["veg_dense_forest"]
                if suffix == "dark"
                else config.palette["veg_dense_trees_grass"]
            )
            draw.polygon(pts, fill=fill)

    for feat in layers.tree_lines:
        pts = _feature_points(feat, config)
        if len(pts) >= 2:
            mx = sum(x for x, _ in pts) // len(pts)
            my = sum(y for _, y in pts) // len(pts)
            suffix = _ground_suffix(mx, my, masks)
            fill = (
                config.palette["veg_fir_trees_grass"]
                if suffix == "dark"
                else config.palette["veg_trees_grass"]
            )
            draw.line(pts, fill=fill, width=4)

    for feat in layers.tree_points:
        pts = _feature_points(feat, config)
        if pts:
            x, y = pts[0]
            suffix = _ground_suffix(x, y, masks)
            fill = (
                config.palette["veg_fir_trees_grass"]
                if suffix == "dark"
                else config.palette["veg_trees_grass"]
            )
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=fill)

    return image
