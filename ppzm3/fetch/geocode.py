from __future__ import annotations

import math
from typing import Any

import requests

from ppzm3.config import AppConfig
from ppzm3.types import BBox


def geocode_zip_center(config: AppConfig) -> tuple[float, float]:
    params = {
        "postalcode": config.zip_code,
        "countrycodes": config.country_code,
        "format": "jsonv2",
        "limit": 1,
    }
    response = requests.get(
        config.nominatim_url,
        params=params,
        headers={"User-Agent": config.user_agent},
        timeout=60,
    )
    response.raise_for_status()
    payload: list[dict[str, Any]] = response.json()
    if not payload:
        raise RuntimeError(f"Unable to geocode ZIP code {config.zip_code}")
    return float(payload[0]["lat"]), float(payload[0]["lon"])


def build_bbox_from_center(
    center_lat: float,
    center_lon: float,
    cells_x: int,
    cells_y: int,
    tiles_per_cell: int,
    meters_per_tile: float,
) -> BBox:
    width_m = cells_x * tiles_per_cell * meters_per_tile
    height_m = cells_y * tiles_per_cell * meters_per_tile

    lat_deg_per_m = 1.0 / 111_320.0
    lon_deg_per_m = 1.0 / (111_320.0 * math.cos(math.radians(center_lat)))

    half_height_deg = (height_m / 2.0) * lat_deg_per_m
    half_width_deg = (width_m / 2.0) * lon_deg_per_m

    return BBox(
        south=center_lat - half_height_deg,
        west=center_lon - half_width_deg,
        north=center_lat + half_height_deg,
        east=center_lon + half_width_deg,
    )
