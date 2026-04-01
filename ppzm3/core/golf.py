from __future__ import annotations

from PIL import Image, ImageDraw
import numpy as np

from ppzm3.config import AppConfig
from ppzm3.core.geometry import bbox_from_points
from ppzm3.core.osm_parse import parse_features
from ppzm3.types import Feature, GolfLayers, GolfMasks


def _expanded_bbox(points: list[tuple[float, float]], pad_ratio: float = 0.03) -> tuple[float, float, float, float]:
    min_lat, min_lon, max_lat, max_lon = bbox_from_points(points)
    lat_pad = max((max_lat - min_lat) * pad_ratio, 1e-5)
    lon_pad = max((max_lon - min_lon) * pad_ratio, 1e-5)
    return min_lat - lat_pad, min_lon - lon_pad, max_lat + lat_pad, max_lon + lon_pad


def _inside_bbox(feat: Feature, bbox: tuple[float, float, float, float]) -> bool:
    min_lat, min_lon, max_lat, max_lon = bbox
    for lat, lon in feat.geometry:
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return True
    return False


def normalize_golf_data(raw_osm: dict, config: AppConfig) -> GolfLayers:
    features = parse_features(raw_osm)
    layers = GolfLayers()

    course_polygons = [
        feat for feat in features
        if feat.tags.get("leisure") == "golf_course"
        and config.golf_course_name.lower() in feat.tags.get("name", "").lower()
    ]
    if not course_polygons:
        course_polygons = [feat for feat in features if feat.tags.get("leisure") == "golf_course"]
    if not course_polygons:
        raise RuntimeError("No golf course boundary found in OSM payload.")

    boundary_points = [pt for feat in course_polygons for pt in feat.geometry]
    filter_bbox = _expanded_bbox(boundary_points)
    layers.course_polygons.extend(course_polygons)

    for feat in features:
        tags = feat.tags
        if not _inside_bbox(feat, filter_bbox):
            continue
        golf = tags.get("golf")
        natural = tags.get("natural")
        landuse = tags.get("landuse")
        waterway = tags.get("waterway")
        highway = tags.get("highway")

        if golf == "fairway":
            layers.fairways.append(feat)
        elif golf == "green":
            layers.greens.append(feat)
        elif golf in {"tee", "driving_range"}:
            layers.tees.append(feat)
        elif golf in {"bunker", "sand_trap"} or natural == "sand":
            layers.sand.append(feat)
        elif natural == "water" or waterway:
            layers.water.append(feat)
        elif highway in {"path", "service", "track"} or golf in {"cartpath", "path"}:
            layers.paths.append(feat)
        elif landuse == "forest" or natural == "wood" or natural == "tree_row":
            layers.woods.append(feat)
        elif golf in {"rough", "semi_rough"}:
            layers.rough.append(feat)

    return layers


def _all_detail_points(layers: GolfLayers) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for bucket in (
        layers.fairways,
        layers.greens,
        layers.tees,
        layers.sand,
        layers.water,
        layers.paths,
        layers.woods,
        layers.rough,
    ):
        for feat in bucket:
            points.extend(feat.geometry)
    if not points:
        points = [pt for feat in layers.course_polygons for pt in feat.geometry]
    if not points:
        raise RuntimeError("No golf detail geometry found in OSM payload.")
    return points


def _fit_points(
    feat: Feature,
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    width: int,
    height: int,
    pad: int,
) -> list[tuple[int, int]]:
    pts: list[tuple[int, int]] = []
    lon_span = max(max_lon - min_lon, 1e-9)
    lat_span = max(max_lat - min_lat, 1e-9)

    for lat, lon in feat.geometry:
        x = pad + int(round(((lon - min_lon) / lon_span) * max(1, width - 1 - 2 * pad)))
        y = pad + int(round(((max_lat - lat) / lat_span) * max(1, height - 1 - 2 * pad)))
        pts.append((x, y))
    return pts


def render_golf_overlay(layers: GolfLayers, config: AppConfig):
    points = _all_detail_points(layers)
    min_lat, min_lon, max_lat, max_lon = bbox_from_points(points)
    lat_span = max_lat - min_lat
    lon_span = max_lon - min_lon
    aspect = lon_span / max(lat_span, 1e-9)

    max_dim = 1200
    if aspect >= 1.0:
        width = max_dim
        height = max(220, int(max_dim / max(aspect, 1e-9)))
    else:
        height = max_dim
        width = max(220, int(max_dim * aspect))

    image = Image.new("RGBA", (width + 2 * config.golf_padding_tiles, height + 2 * config.golf_padding_tiles), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    footprint = Image.new("L", image.size, 0)
    footprint_draw = ImageDraw.Draw(footprint)
    water_mask = Image.new("L", image.size, 0)
    water_draw = ImageDraw.Draw(water_mask)

    def render_bucket(bucket: list[Feature], fill: tuple[int, int, int], width_px: int = 4, paint_footprint: bool = True):
        for feat in bucket:
            pts = _fit_points(
                feat,
                min_lat=min_lat,
                min_lon=min_lon,
                max_lat=max_lat,
                max_lon=max_lon,
                width=image.size[0],
                height=image.size[1],
                pad=config.golf_padding_tiles,
            )
            if len(pts) < 2:
                continue
            if feat.closed and len(pts) >= 3:
                draw.polygon(pts, fill=fill + (255,))
                if paint_footprint:
                    footprint_draw.polygon(pts, fill=255)
            else:
                draw.line(pts, fill=fill + (255,), width=width_px)
                if paint_footprint:
                    footprint_draw.line(pts, fill=255, width=max(width_px, 5))

    # Intentionally DO NOT paint the outer course boundary as the visible footprint.
    render_bucket(layers.woods, config.palette["forest"], paint_footprint=False)
    render_bucket(layers.rough, config.palette["golf_rough"])
    render_bucket(layers.fairways, config.palette["golf_fairway"])
    render_bucket(layers.greens, config.palette["golf_green"])
    render_bucket(layers.tees, config.palette["golf_tee"])
    render_bucket(layers.sand, config.palette["golf_sand"])
    render_bucket(layers.paths, config.palette["golf_path"], width_px=3)

    for feat in layers.water:
        pts = _fit_points(
            feat,
            min_lat=min_lat,
            min_lon=min_lon,
            max_lat=max_lat,
            max_lon=max_lon,
            width=image.size[0],
            height=image.size[1],
            pad=config.golf_padding_tiles,
        )
        if len(pts) < 2:
            continue
        if feat.closed and len(pts) >= 3:
            draw.polygon(pts, fill=config.palette["water"] + (255,))
            footprint_draw.polygon(pts, fill=255)
            water_draw.polygon(pts, fill=255)
        else:
            draw.line(pts, fill=config.palette["water"] + (255,), width=5)
            footprint_draw.line(pts, fill=255, width=7)
            water_draw.line(pts, fill=255, width=7)

    return image, GolfMasks(
        footprint_mask=np.array(footprint, dtype=np.uint8),
        water_mask=np.array(water_mask, dtype=np.uint8),
    )
