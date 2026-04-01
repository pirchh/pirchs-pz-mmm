from __future__ import annotations

import logging

import numpy as np
from PIL import Image

from ppzm3.config import AppConfig
from ppzm3.types import Placement

log = logging.getLogger("ppzm3.placement")


def _integral(arr: np.ndarray) -> np.ndarray:
    src = arr.astype(np.int64, copy=False)
    return src.cumsum(axis=0, dtype=np.int64).cumsum(axis=1, dtype=np.int64)


def _window_sum(integral: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> int:
    total = integral[y1 - 1, x1 - 1]
    if x0 > 0:
        total -= integral[y1 - 1, x0 - 1]
    if y0 > 0:
        total -= integral[y0 - 1, x1 - 1]
    if x0 > 0 and y0 > 0:
        total += integral[y0 - 1, x0 - 1]
    return int(total)


def find_best_golf_placement(
    forest_mask: np.ndarray,
    blocked_mask: np.ndarray,
    golf_mask: np.ndarray,
    config: AppConfig,
) -> Placement:
    log.info("Golf placement: preparing candidate scan...")
    footprint = (golf_mask > 0).astype(np.uint8)
    h, w = footprint.shape
    grid_h, grid_w = forest_mask.shape

    if h >= grid_h or w >= grid_w:
        raise RuntimeError("Golf overlay is larger than the overview grid.")

    forest = (forest_mask > 200).astype(np.uint8)
    blocked = (blocked_mask > 0).astype(np.uint8)

    forest_i = _integral(forest)
    blocked_i = _integral(blocked)

    best = Placement(x=0, y=0, score=-10**9)
    step = 25
    candidates = max(1, ((grid_h - h + step - 1) // step) * ((grid_w - w + step - 1) // step))
    checked = 0
    log.info("Golf placement: scanning %d candidates with step=%d...", candidates, step)

    for y in range(0, grid_h - h, step):
        for x in range(0, grid_w - w, step):
            checked += 1
            if checked == 1 or checked % 500 == 0 or checked == candidates:
                log.info("Golf placement: checked %d/%d candidates...", checked, candidates)
            forest_score = _window_sum(forest_i, x, y, x + w, y + h)
            blocked_score = _window_sum(blocked_i, x, y, x + w, y + h)
            score = forest_score - (blocked_score * 50)
            if blocked_score == 0 and score > best.score:
                best = Placement(x=x, y=y, score=score)

    if best.score < 0:
        log.info("Golf placement: no zero-block candidates found, falling back to least-blocked search...")
        # Fallback: accept the least blocked location.
        least_blocked = Placement(x=0, y=0, score=10**9)
        checked = 0
        for y in range(0, grid_h - h, step):
            for x in range(0, grid_w - w, step):
                checked += 1
                if checked == 1 or checked % 500 == 0 or checked == candidates:
                    log.info("Golf placement fallback: checked %d/%d candidates...", checked, candidates)
                blocked_score = _window_sum(blocked_i, x, y, x + w, y + h)
                if blocked_score < least_blocked.score:
                    least_blocked = Placement(x=x, y=y, score=blocked_score)
        log.info("Golf placement fallback complete: x=%d y=%d blocked=%d", least_blocked.x, least_blocked.y, least_blocked.score)
        return least_blocked
    log.info("Golf placement complete: x=%d y=%d score=%d", best.x, best.y, best.score)
    return best


def paste_golf_overlay(
    base: Image.Image,
    golf_overlay: Image.Image,
    golf_footprint: np.ndarray,
    placement: Placement,
) -> Image.Image:
    result = base.copy().convert("RGBA")
    x, y = placement.x, placement.y
    result.alpha_composite(golf_overlay, dest=(x, y))
    return result.convert("RGB")
