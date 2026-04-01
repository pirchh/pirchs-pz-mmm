from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import requests

from ppzm3.config import AppConfig
from ppzm3.core.geometry import bbox_from_points
from ppzm3.core.osm_parse import parse_features

log = logging.getLogger("ppzm3.osm")


def _cache_path(config: AppConfig, stem: str) -> Path:
    return config.cache_dir / f"{config.map_name}_{stem}.json"


def _post_overpass(query: str, config: AppConfig) -> dict[str, Any]:
    response = requests.post(
        config.overpass_url,
        data={"data": query},
        headers={"User-Agent": config.user_agent},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def _expand_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float, meters: float) -> tuple[float, float, float, float]:
    center_lat = (min_lat + max_lat) / 2.0
    lat_pad = meters / 111_320.0
    lon_pad = meters / (111_320.0 * max(0.2, math.cos(math.radians(center_lat))))
    return min_lat - lat_pad, min_lon - lon_pad, max_lat + lat_pad, max_lon + lon_pad


def fetch_nature_data(config: AppConfig) -> dict[str, Any]:
    cache_path = _cache_path(config, "nature_raw")
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    bbox = config.bbox.as_overpass()
    query = f"""
[out:json][timeout:180];
(
  way["natural"="water"]({bbox});
  relation["natural"="water"]({bbox});
  way["waterway"]({bbox});
  way["landuse"="forest"]({bbox});
  relation["landuse"="forest"]({bbox});
  way["natural"="wood"]({bbox});
  relation["natural"="wood"]({bbox});
  way["natural"="tree_row"]({bbox});
  way["natural"="scrub"]({bbox});
  relation["natural"="scrub"]({bbox});
  way["landuse"="grass"]({bbox});
  relation["landuse"="grass"]({bbox});
  way["landuse"="meadow"]({bbox});
  relation["landuse"="meadow"]({bbox});
  way["landuse"="farmland"]({bbox});
  relation["landuse"="farmland"]({bbox});
  way["natural"="grassland"]({bbox});
  relation["natural"="grassland"]({bbox});
  way["leisure"="park"]({bbox});
  relation["leisure"="park"]({bbox});
  node["natural"="tree"]({bbox});
);
(._;>;);
out body;
"""
    payload = _post_overpass(query, config)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def fetch_golf_course_data(config: AppConfig) -> dict[str, Any]:
    cache_path = _cache_path(config, "golf_raw")
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    lat = config.center_lat
    lon = config.center_lon
    radius = config.golf_search_radius_m
    name = config.golf_course_name.replace('"', '\"')

    boundary_query = f"""
[out:json][timeout:180];
(
  way["leisure"="golf_course"]["name"~"^{name}$",i](around:{radius},{lat},{lon});
  relation["leisure"="golf_course"]["name"~"^{name}$",i](around:{radius},{lat},{lon});
);
(._;>;);
out body;
"""
    boundary_payload = _post_overpass(boundary_query, config)
    boundary_features = [
        feat for feat in parse_features(boundary_payload)
        if feat.tags.get("leisure") == "golf_course" and feat.tags.get("name", "").lower() == config.golf_course_name.lower()
    ]
    if not boundary_features:
        raise RuntimeError(f"Could not locate named golf course boundary for {config.golf_course_name}.")

    boundary_points = [pt for feat in boundary_features for pt in feat.geometry]
    min_lat, min_lon, max_lat, max_lon = bbox_from_points(boundary_points)
    min_lat, min_lon, max_lat, max_lon = _expand_bbox(min_lat, min_lon, max_lat, max_lon, config.golf_bbox_expand_m)
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"

    detail_query = f"""
[out:json][timeout:180];
(
  way["leisure"="golf_course"]({bbox});
  relation["leisure"="golf_course"]({bbox});
  way["golf"]({bbox});
  relation["golf"]({bbox});
  way["natural"="water"]({bbox});
  relation["natural"="water"]({bbox});
  way["waterway"]({bbox});
  relation["waterway"]({bbox});
  way["landuse"="forest"]({bbox});
  relation["landuse"="forest"]({bbox});
  way["natural"="wood"]({bbox});
  relation["natural"="wood"]({bbox});
  way["natural"="tree_row"]({bbox});
);
(._;>;);
out body;
"""
    payload = _post_overpass(detail_query, config)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload
