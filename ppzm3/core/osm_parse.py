from __future__ import annotations

from collections import defaultdict
from typing import Any

from ppzm3.types import Feature


def build_node_lookup(elements: list[dict[str, Any]]) -> dict[int, tuple[float, float]]:
    lookup: dict[int, tuple[float, float]] = {}
    for elem in elements:
        if elem.get("type") == "node":
            lookup[int(elem["id"])] = (float(elem["lat"]), float(elem["lon"]))
    return lookup


def build_way_lookup(elements: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(elem["id"]): elem for elem in elements if elem.get("type") == "way"}


def parse_features(payload: dict[str, Any]) -> list[Feature]:
    elements: list[dict[str, Any]] = payload.get("elements", [])
    node_lookup = build_node_lookup(elements)
    way_lookup = build_way_lookup(elements)
    relation_members: dict[int, list[list[tuple[float, float]]]] = defaultdict(list)
    features: list[Feature] = []

    for elem in elements:
        etype = elem.get("type")
        tags = elem.get("tags", {})
        if etype == "way":
            nodes = elem.get("nodes", [])
            geometry = [node_lookup[nid] for nid in nodes if nid in node_lookup]
            if len(geometry) >= 2:
                closed = len(geometry) >= 4 and geometry[0] == geometry[-1]
                features.append(
                    Feature(
                        tags=tags,
                        geometry=geometry,
                        feature_type="way",
                        closed=closed,
                    )
                )
        elif etype == "relation":
            members = elem.get("members", [])
            combined: list[tuple[float, float]] = []
            for member in members:
                if member.get("type") != "way":
                    continue
                way = way_lookup.get(int(member["ref"]))
                if not way:
                    continue
                points = [node_lookup[nid] for nid in way.get("nodes", []) if nid in node_lookup]
                if len(points) >= 2:
                    relation_members[int(elem["id"])].append(points)
                    combined.extend(points)
            if len(combined) >= 4:
                closed = combined[0] == combined[-1]
                features.append(
                    Feature(
                        tags=tags,
                        geometry=combined,
                        feature_type="relation",
                        closed=closed,
                    )
                )
        elif etype == "node" and tags:
            features.append(
                Feature(
                    tags=tags,
                    geometry=[(float(elem["lat"]), float(elem["lon"]))],
                    feature_type="node",
                    closed=False,
                )
            )
    return features
