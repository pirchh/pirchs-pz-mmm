from typing import Any

from ppzm3.config import AppConfig
from ppzm3.types import NormalizedLayers


def _index_nodes(elements: list[dict[str, Any]]) -> dict[int, tuple[float, float]]:
    nodes: dict[int, tuple[float, float]] = {}
    for el in elements:
        if el.get("type") == "node":
            node_id = el.get("id")
            lat = el.get("lat")
            lon = el.get("lon")
            if node_id is not None and lat is not None and lon is not None:
                nodes[node_id] = (lat, lon)
    return nodes


def _way_to_coords(way: dict[str, Any], node_index: dict[int, tuple[float, float]]) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    for node_id in way.get("nodes", []):
        pt = node_index.get(node_id)
        if pt is not None:
            coords.append(pt)
    return coords


def _classify_landuse_kind(tags: dict[str, Any]) -> str | None:
    # Special cases first
    if tags.get("leisure") == "golf_course":
        return "golf"

    if "landuse" in tags:
        return str(tags["landuse"])

    if "natural" in tags:
        return str(tags["natural"])

    if tags.get("leisure") == "park":
        return "park"

    return None


def normalize_osm_data(raw_osm: dict[str, Any], config: AppConfig) -> NormalizedLayers:
    elements = raw_osm.get("elements", [])
    node_index = _index_nodes(elements)

    roads: list[dict[str, Any]] = []
    water: list[dict[str, Any]] = []
    landuse: list[dict[str, Any]] = []
    buildings: list[dict[str, Any]] = []

    for el in elements:
        if el.get("type") != "way":
            continue

        tags = el.get("tags", {})
        coords = _way_to_coords(el, node_index)
        if len(coords) < 2:
            continue

        if "highway" in tags:
            roads.append(
                {
                    "id": el.get("id"),
                    "kind": tags.get("highway", "unclassified"),
                    "coords": coords,
                    "tags": tags,
                }
            )
            continue

        if "waterway" in tags or tags.get("natural") == "water":
            water.append(
                {
                    "id": el.get("id"),
                    "kind": tags.get("waterway", tags.get("natural", "water")),
                    "coords": coords,
                    "tags": tags,
                }
            )
            continue

        landuse_kind = _classify_landuse_kind(tags)
        if landuse_kind is not None:
            landuse.append(
                {
                    "id": el.get("id"),
                    "kind": landuse_kind,
                    "coords": coords,
                    "tags": tags,
                }
            )
            continue

        if "building" in tags:
            buildings.append(
                {
                    "id": el.get("id"),
                    "kind": tags.get("building", "yes"),
                    "coords": coords,
                    "tags": tags,
                }
            )

    print(
        f"Normalized: roads={len(roads)}, water={len(water)}, "
        f"landuse={len(landuse)}, buildings={len(buildings)}"
    )

    return NormalizedLayers(
        roads=roads,
        water=water,
        landuse=landuse,
        buildings=buildings,
    )