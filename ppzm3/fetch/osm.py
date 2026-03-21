import json
import time
from pathlib import Path
from typing import Any

import requests

from ppzm3.config import AppConfig


OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def build_overpass_query(config: AppConfig) -> str:
    s, w, n, e = config.bbox.as_overpass_tuple()

    return f"""
[out:json][timeout:90];
(
  way["highway"]({s},{w},{n},{e});
  way["waterway"]({s},{w},{n},{e});
  way["natural"="water"]({s},{w},{n},{e});
  way["landuse"]({s},{w},{n},{e});
  way["natural"="wood"]({s},{w},{n},{e});
  way["building"]({s},{w},{n},{e});
);
(._;>;);
out body;
"""


def cache_file_path(config: AppConfig) -> Path:
    return config.cache_dir / f"{config.map_name}_osm_raw.json"


def _fetch_from_endpoint(endpoint: str, query: str) -> dict[str, Any]:
    response = requests.post(
        endpoint,
        data={"data": query},
        timeout=180,
        headers={
            "User-Agent": "ppzm3/0.1 (Project Zomboid map prototype)"
        },
    )
    response.raise_for_status()
    return response.json()


def fetch_osm_data(config: AppConfig, force_refresh: bool = False) -> dict[str, Any]:
    cache_path = cache_file_path(config)

    if cache_path.exists() and not force_refresh:
        print(f"Loading cached OSM data: {cache_path}")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    query = build_overpass_query(config)
    errors: list[str] = []

    for endpoint in OVERPASS_ENDPOINTS:
        print(f"Trying Overpass endpoint: {endpoint}")
        try:
            payload = _fetch_from_endpoint(endpoint, query)
            cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"Cached OSM data to: {cache_path}")
            return payload
        except requests.RequestException as exc:
            error_text = f"{endpoint} -> {exc}"
            print(f"Failed: {error_text}")
            errors.append(error_text)
            time.sleep(2)

    joined = "\n".join(errors)
    raise RuntimeError(
        "All Overpass endpoints failed.\n"
        "This usually means the query area is too large or the public servers are overloaded.\n\n"
        f"Failures:\n{joined}"
    )