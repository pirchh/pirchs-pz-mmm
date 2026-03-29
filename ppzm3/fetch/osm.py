import json
import time
from pathlib import Path
from typing import Any

import requests

from ppzm3.config import AppConfig


DEFAULT_OVERPASS_ENDPOINTS = [
    "https://z.overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def build_overpass_query(config: AppConfig) -> str:
    if config.bbox is None:
        raise ValueError("config.bbox must be set before building an Overpass query")

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
""".strip()


def cache_file_path(config: AppConfig) -> Path:
    return config.cache_dir / f"{config.map_name}_osm_raw.json"


def get_overpass_endpoints(config: AppConfig) -> list[str]:
    endpoints: list[str] = []

    if config.overpass_url:
        endpoints.append(config.overpass_url)

    for endpoint in DEFAULT_OVERPASS_ENDPOINTS:
        if endpoint not in endpoints:
            endpoints.append(endpoint)

    return endpoints


def _response_preview(response: requests.Response, limit: int = 300) -> str:
    text = response.text[:limit]
    return text.replace("\r", " ").replace("\n", " ").strip()


def _fetch_from_endpoint(
    endpoint: str,
    query: str,
    user_agent: str,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    response = requests.post(
        endpoint,
        data={"data": query},
        timeout=timeout_seconds,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json,text/plain,*/*",
        },
    )

    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        content_type = response.headers.get("Content-Type", "")
        preview = _response_preview(response)
        raise RuntimeError(
            f"Non-JSON response from {endpoint} "
            f"(status={response.status_code}, content-type={content_type!r}): {preview}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Unexpected JSON payload type from {endpoint}: {type(payload).__name__}"
        )

    if "elements" not in payload:
        keys = ", ".join(sorted(payload.keys()))
        raise RuntimeError(
            f"JSON payload from {endpoint} did not contain 'elements'. Keys: {keys}"
        )

    return payload


def _load_cached_osm(cache_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Cached OSM file exists but is invalid JSON: {cache_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Cached OSM file is not a JSON object: {cache_path}"
        )

    return payload


def fetch_osm_data(config: AppConfig, force_refresh: bool = False) -> dict[str, Any]:
    cache_path = cache_file_path(config)

    if cache_path.exists() and not force_refresh:
        print(f"Loading cached OSM data: {cache_path}")
        return _load_cached_osm(cache_path)

    query = build_overpass_query(config)
    endpoints = get_overpass_endpoints(config)

    errors: list[str] = []
    base_sleep_seconds = 2.0
    max_attempts_per_endpoint = 2

    for endpoint in endpoints:
        for attempt in range(1, max_attempts_per_endpoint + 1):
            print(
                f"Trying Overpass endpoint: {endpoint} "
                f"(attempt {attempt}/{max_attempts_per_endpoint})"
            )

            try:
                payload = _fetch_from_endpoint(
                    endpoint=endpoint,
                    query=query,
                    user_agent=config.user_agent,
                    timeout_seconds=180,
                )

                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps(payload, indent=2),
                    encoding="utf-8",
                )
                print(f"Cached OSM data to: {cache_path}")
                return payload

            except Exception as exc:
                error_text = (
                    f"{endpoint} [attempt {attempt}/{max_attempts_per_endpoint}] -> {exc}"
                )
                print(f"Failed: {error_text}")
                errors.append(error_text)

                if attempt < max_attempts_per_endpoint:
                    sleep_seconds = base_sleep_seconds * (2 ** (attempt - 1))
                    print(f"Retrying in {sleep_seconds:.1f} sec...")
                    time.sleep(sleep_seconds)
                else:
                    time.sleep(base_sleep_seconds)

    joined = "\n".join(errors)
    raise RuntimeError(
        "All Overpass endpoints failed.\n"
        "This usually means the public servers are overloaded, rate-limited, "
        "or returned non-JSON error content.\n\n"
        f"Failures:\n{joined}"
    )