import json
from pathlib import Path
from typing import Any

import requests

from ppzm3.config import AppConfig
from ppzm3.types import BBox


def _zip_cache_path(config: AppConfig) -> Path:
    return config.cache_dir / f"zip_{config.country_code}_{config.zip_code}.json"


def geocode_zip_center(config: AppConfig, force_refresh: bool = False) -> tuple[float, float]:
    cache_path = _zip_cache_path(config)

    if cache_path.exists() and not force_refresh:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        return float(payload["lat"]), float(payload["lon"])

    params = {
        "q": f"{config.zip_code}, {config.country_code.upper()}",
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
    }

    response = requests.get(
        config.nominatim_url,
        params=params,
        timeout=60,
        headers={"User-Agent": config.user_agent},
    )
    response.raise_for_status()

    results: list[dict[str, Any]] = response.json()
    if not results:
        raise RuntimeError(f"Could not geocode ZIP code {config.zip_code}")

    item = results[0]
    lat = float(item["lat"])
    lon = float(item["lon"])

    cache_path.write_text(
        json.dumps({"lat": lat, "lon": lon, "raw": item}, indent=2),
        encoding="utf-8",
    )

    return lat, lon


def miles_per_degree_lat() -> float:
    return 69.0


def miles_per_degree_lon(lat: float) -> float:
    import math
    return 69.172 * math.cos(math.radians(lat))


def build_bbox_from_center(lat: float, lon: float, cells_x: int, cells_y: int, tiles_per_cell: int) -> BBox:
    total_width_m = cells_x * tiles_per_cell
    total_height_m = cells_y * tiles_per_cell

    half_width_miles = (total_width_m / 1609.34) / 2.0
    half_height_miles = (total_height_m / 1609.34) / 2.0

    lat_deg = half_height_miles / miles_per_degree_lat()
    lon_deg = half_width_miles / miles_per_degree_lon(lat)

    return BBox(
        south=lat - lat_deg,
        west=lon - lon_deg,
        north=lat + lat_deg,
        east=lon + lon_deg,
    )