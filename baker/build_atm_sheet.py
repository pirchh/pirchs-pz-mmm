from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps, ImageDraw


# ============================================================
# Canvas / lane layout
# ============================================================

SHEET_W = 1024
SHEET_H = 2048

# One ATM variant per 128px lane across the sheet.
LANE_W = 128
ROW_H = 128

COLS = SHEET_W // LANE_W   # 8
ROWS = SHEET_H // ROW_H    # 16

DEFAULT_BOTTOM_PAD = 4
DEFAULT_MAX_ATM_W = 72
DEFAULT_MAX_ATM_H = 108


# ============================================================
# Helpers
# ============================================================

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Expected 6-digit hex color, got: {value}")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def ensure_rgba(img: Image.Image) -> Image.Image:
    return img.convert("RGBA") if img.mode != "RGBA" else img


def trim_transparent(img: Image.Image) -> Image.Image:
    img = ensure_rgba(img)
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("Image is fully transparent.")
    return img.crop(bbox)


def remove_background_by_corner_sample(
    img: Image.Image,
    tolerance: int = 8,
    alpha_cutoff: int = 10,
    edge_only: bool = True,
    edge_band: int = 6,
) -> Image.Image:
    """
    Remove likely background pixels by sampling the four corners.

    Safer than the old version because:
    - lower tolerance
    - can limit removal to the outer edge band only
    - preserves interior gray ATM body pixels much better
    """
    img = ensure_rgba(img)
    w, h = img.size

    samples = [
        img.getpixel((0, 0)),
        img.getpixel((w - 1, 0)),
        img.getpixel((0, h - 1)),
        img.getpixel((w - 1, h - 1)),
    ]

    br = sum(px[0] for px in samples) // 4
    bg = sum(px[1] for px in samples) // 4
    bb = sum(px[2] for px in samples) // 4

    out = Image.new("RGBA", img.size)

    for y in range(h):
        for x in range(w):
            r, g, b, a = img.getpixel((x, y))

            if a <= alpha_cutoff:
                out.putpixel((x, y), (0, 0, 0, 0))
                continue

            is_edge_pixel = (
                x < edge_band
                or x >= w - edge_band
                or y < edge_band
                or y >= h - edge_band
            )

            should_test_bg = is_edge_pixel if edge_only else True

            if should_test_bg and (
                abs(r - br) <= tolerance
                and abs(g - bg) <= tolerance
                and abs(b - bb) <= tolerance
            ):
                out.putpixel((x, y), (0, 0, 0, 0))
            else:
                out.putpixel((x, y), (r, g, b, a))

    return out


def fit_inside(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    img = ensure_rgba(img)
    w, h = img.size
    scale = min(max_w / w, max_h / h)
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def quantize_alpha_grayscale(img: Image.Image, steps: int = 10) -> Image.Image:
    img = ensure_rgba(img)
    r, g, b, a = img.split()
    gray = ImageOps.grayscale(Image.merge("RGB", (r, g, b)))

    gray_data = list(gray.getdata())
    quantized = []

    for px in gray_data:
        bucket = round((px / 255) * (steps - 1))
        val = round((bucket / (steps - 1)) * 255)
        quantized.append(val)

    gray_q = Image.new("L", gray.size)
    gray_q.putdata(quantized)

    return Image.merge("RGBA", (gray_q, gray_q, gray_q, a))


def build_exact_gray_ramp(levels: int) -> list[int]:
    return [round((i / (levels - 1)) * 255) for i in range(levels)]


def remap_grayscale_to_palette(img: Image.Image, palette_hex: list[str]) -> Image.Image:
    img = ensure_rgba(img)
    palette = [hex_to_rgb(c) for c in palette_hex]
    steps = len(palette)
    gray_ramp = build_exact_gray_ramp(steps)

    out = Image.new("RGBA", img.size)
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = img.getpixel((x, y))
            if a == 0:
                out.putpixel((x, y), (0, 0, 0, 0))
                continue

            luminance = r
            idx = min(range(steps), key=lambda i: abs(gray_ramp[i] - luminance))
            pr, pg, pb = palette[idx]
            out.putpixel((x, y), (pr, pg, pb, a))

    return out


def tint_region_by_luminance(
    img: Image.Image,
    tint_hex: str,
    min_luma: int,
    max_luma: int,
    strength: float = 0.70,
) -> Image.Image:
    img = ensure_rgba(img)
    tr, tg, tb = hex_to_rgb(tint_hex)
    out = Image.new("RGBA", img.size)

    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = img.getpixel((x, y))
            if a == 0:
                out.putpixel((x, y), (0, 0, 0, 0))
                continue

            luma = round(0.299 * r + 0.587 * g + 0.114 * b)
            if min_luma <= luma <= max_luma:
                nr = round(r * (1.0 - strength) + tr * strength)
                ng = round(g * (1.0 - strength) + tg * strength)
                nb = round(b * (1.0 - strength) + tb * strength)
                out.putpixel((x, y), (nr, ng, nb, a))
            else:
                out.putpixel((x, y), (r, g, b, a))

    return out


# ============================================================
# Palette specs
# ============================================================

@dataclass
class PaletteSpec:
    name: str
    ramp: list[str]
    accent_hex: str | None = None
    accent_min_luma: int = 150
    accent_max_luma: int = 255
    accent_strength: float = 0.70


DEFAULT_PALETTES: list[PaletteSpec] = [
    PaletteSpec(
        name="atm_blue",
        ramp=[
            "#12161b", "#18202a", "#1d2938", "#22344b", "#2a4160",
            "#34507a", "#43689b", "#5f88c2", "#8cb3ea", "#d8e8ff",
        ],
        accent_hex="#8fdc3c",
    ),
    PaletteSpec(
        name="atm_navy",
        ramp=[
            "#0c1015", "#101721", "#162030", "#1b2a40", "#223454",
            "#2b4269", "#385681", "#5274a7", "#82a0c8", "#d2dce9",
        ],
        accent_hex="#8fdc3c",
    ),
    PaletteSpec(
        name="atm_gray",
        ramp=[
            "#151515", "#232323", "#313131", "#424242", "#565656",
            "#6b6b6b", "#858585", "#a3a3a3", "#c7c7c7", "#efefef",
        ],
        accent_hex="#98df45",
    ),
    PaletteSpec(
        name="atm_silver",
        ramp=[
            "#1d1d1d", "#2c2c2c", "#3e3e3e", "#545454", "#6c6c6c",
            "#858585", "#a2a2a2", "#bcbcbc", "#d7d7d7", "#f5f5f5",
        ],
        accent_hex="#98df45",
    ),
    PaletteSpec(
        name="atm_red",
        ramp=[
            "#1e1010", "#301515", "#471c1c", "#612323", "#7b2b2b",
            "#983434", "#b74444", "#d26767", "#e7a0a0", "#f7dada",
        ],
        accent_hex="#ece56e",
    ),
    PaletteSpec(
        name="atm_green",
        ramp=[
            "#111611", "#182419", "#213223", "#29412e", "#32523a",
            "#3d6647", "#4c7f58", "#6aa075", "#9ac9a2", "#e0f1e2",
        ],
        accent_hex="#c9f36a",
    ),
    PaletteSpec(
        name="atm_black",
        ramp=[
            "#090909", "#111111", "#1b1b1b", "#252525", "#313131",
            "#404040", "#525252", "#6d6d6d", "#969696", "#d6d6d6",
        ],
        accent_hex="#78d7ff",
    ),
    PaletteSpec(
        name="atm_white",
        ramp=[
            "#202020", "#323232", "#474747", "#5f5f5f", "#7a7a7a",
            "#979797", "#b5b5b5", "#d0d0d0", "#e9e9e9", "#ffffff",
        ],
        accent_hex="#8fdc3c",
    ),
]


# ============================================================
# Placement
# ============================================================

def paste_in_lane(
    sheet: Image.Image,
    sprite: Image.Image,
    col: int,
    row: int,
    lane_w: int = LANE_W,
    row_h: int = ROW_H,
    bottom_pad: int = DEFAULT_BOTTOM_PAD,
) -> None:
    lane_x = col * lane_w
    row_y = row * row_h

    x = lane_x + (lane_w - sprite.width) // 2
    y = row_y + row_h - sprite.height - bottom_pad

    sheet.alpha_composite(sprite, (x, y))


def draw_debug_grid(img: Image.Image) -> Image.Image:
    out = img.copy()
    draw = ImageDraw.Draw(out)

    for x in range(0, out.width, LANE_W):
        draw.line([(x, 0), (x, out.height)], fill=(255, 0, 0, 180), width=1)

    for y in range(0, out.height, ROW_H):
        draw.line([(0, y), (out.width, y)], fill=(255, 0, 0, 180), width=1)

    return out


# ============================================================
# Build one variant
# ============================================================

def make_variant(
    master: Image.Image,
    palette: PaletteSpec,
    max_w: int,
    max_h: int,
    gray_steps: int = 10,
    auto_remove_bg: bool = True,
) -> Image.Image:
    work = ensure_rgba(master)

    if auto_remove_bg:
        work = remove_background_by_corner_sample(
            work,
            tolerance=8,
            edge_only=True,
            edge_band=6,
        )

    work = trim_transparent(work)
    work = fit_inside(work, max_w=max_w, max_h=max_h)
    work = quantize_alpha_grayscale(work, steps=gray_steps)
    work = remap_grayscale_to_palette(work, palette.ramp)

    if palette.accent_hex:
        work = tint_region_by_luminance(
            work,
            tint_hex=palette.accent_hex,
            min_luma=palette.accent_min_luma,
            max_luma=palette.accent_max_luma,
            strength=palette.accent_strength,
        )

    return work


# ============================================================
# Build full sheet
# ============================================================

def build_sheet(
    master_path: Path,
    output_path: Path,
    palettes: Iterable[PaletteSpec],
    max_w: int = DEFAULT_MAX_ATM_W,
    max_h: int = DEFAULT_MAX_ATM_H,
    bottom_pad: int = DEFAULT_BOTTOM_PAD,
    start_col: int = 0,
    start_row: int = 0,
    debug_grid: bool = False,
    auto_remove_bg: bool = True,
) -> None:
    master = Image.open(master_path).convert("RGBA")
    sheet = Image.new("RGBA", (SHEET_W, SHEET_H), (0, 0, 0, 0))

    palettes = list(palettes)
    for idx, palette in enumerate(palettes):
        col = start_col + idx
        row = start_row

        if col >= COLS:
            raise ValueError("Not enough horizontal lanes for all ATM variants.")

        variant = make_variant(
            master=master,
            palette=palette,
            max_w=max_w,
            max_h=max_h,
            gray_steps=len(palette.ramp),
            auto_remove_bg=auto_remove_bg,
        )

        paste_in_lane(
            sheet=sheet,
            sprite=variant,
            col=col,
            row=row,
            lane_w=LANE_W,
            row_h=ROW_H,
            bottom_pad=bottom_pad,
        )

    if debug_grid:
        sheet = draw_debug_grid(sheet)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a PZ ATM sheet with 128px horizontal lane spacing."
    )
    parser.add_argument("input", type=Path, help="Path to transparent master ATM PNG")
    parser.add_argument("output", type=Path, help="Output sheet PNG")
    parser.add_argument("--max-atm-width", type=int, default=DEFAULT_MAX_ATM_W)
    parser.add_argument("--max-atm-height", type=int, default=DEFAULT_MAX_ATM_H)
    parser.add_argument("--bottom-pad", type=int, default=DEFAULT_BOTTOM_PAD)
    parser.add_argument("--start-col", type=int, default=0)
    parser.add_argument("--start-row", type=int, default=0)
    parser.add_argument("--debug-grid", action="store_true")
    parser.add_argument("--no-auto-bg-remove", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    build_sheet(
        master_path=args.input,
        output_path=args.output,
        palettes=DEFAULT_PALETTES,
        max_w=args.max_atm_width,
        max_h=args.max_atm_height,
        bottom_pad=args.bottom_pad,
        start_col=args.start_col,
        start_row=args.start_row,
        debug_grid=args.debug_grid,
        auto_remove_bg=not args.no_auto_bg_remove,
    )

    print(f"Wrote sheet to: {args.output}")


if __name__ == "__main__":
    main()