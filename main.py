import logging
import time

from ppzm3.config import AppConfig
from ppzm3.fetch.geocode import build_bbox_from_center, geocode_zip_center
from ppzm3.fetch.osm import fetch_osm_data
from ppzm3.core.normalize import normalize_osm_data
from ppzm3.core.rasterize import (
    crop_center_layers,
    prepare_render_data,
    render_chunk_layers,
)
from ppzm3.core.stylize import stylize_grid
from ppzm3.render.export import (
    build_overview_tiles_from_chunks,
    save_chunk_pair,
)
from ppzm3.render.debug import export_debug_layers


def ensure_dirs(config: AppConfig) -> None:
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    setup_logging()
    log = logging.getLogger("ppzm3")

    config = AppConfig.default()
    ensure_dirs(config)

    center_lat, center_lon = geocode_zip_center(config)
    config.center_lat = center_lat
    config.center_lon = center_lon
    config.bbox = build_bbox_from_center(
        center_lat,
        center_lon,
        config.cells_x,
        config.cells_y,
        config.tiles_per_cell,
    )

    log.info("== ppzm3 OSM Chunk Pipeline ==")
    log.info("Map name: %s", config.map_name)
    log.info("ZIP: %s", config.zip_code)
    log.info("Center: (%s, %s)", config.center_lat, config.center_lon)
    log.info("BBox: %s", config.bbox)
    log.info("Cells: %s x %s", config.cells_x, config.cells_y)
    log.info("Tiles per cell: %s", config.tiles_per_cell)
    log.info("Grid: %s x %s", config.grid_width, config.grid_height)
    log.info("Chunk padding: %s", config.chunk_padding_tiles)
    log.info(
        "Overview block size: %s x %s cells",
        config.overview_block_cells,
        config.overview_block_cells,
    )
    log.info("Preferred Overpass endpoint: %s", config.overpass_url)

    t0 = time.perf_counter()

    raw_osm = fetch_osm_data(config)
    normalized = normalize_osm_data(raw_osm, config)
    prepared = prepare_render_data(normalized, config)

    total_chunks = config.cells_x * config.cells_y
    processed = 0
    render_start = time.perf_counter()

    for cy in range(config.cells_y):
        row_start = time.perf_counter()

        for cx in range(config.cells_x):
            padded_layers = render_chunk_layers(prepared, config, cx, cy)
            styled_padded = stylize_grid(padded_layers, config)
            final_chunk = crop_center_layers(
                styled_padded,
                pad=config.chunk_padding_tiles,
                cell_size=config.tiles_per_cell,
            )

            save_chunk_pair(final_chunk, config, cx, cy)
            processed += 1

            if (
                processed == 1
                or processed % config.log_every_n_chunks == 0
                or processed == total_chunks
            ):
                elapsed = time.perf_counter() - render_start
                rate = processed / elapsed if elapsed > 0 else 0.0
                remaining = total_chunks - processed
                eta_seconds = remaining / rate if rate > 0 else 0.0
                pct = (processed / total_chunks) * 100.0

                log.info(
                    "Chunks: %s/%s (%.1f%%) | %.2f chunks/sec | ETA %.1f min",
                    processed,
                    total_chunks,
                    pct,
                    rate,
                    eta_seconds / 60.0,
                )

        row_elapsed = time.perf_counter() - row_start
        log.info(
            "Completed row %02d/%02d in %.1f sec",
            cy + 1,
            config.cells_y,
            row_elapsed,
        )

    log.info("Chunk export complete. Building overview tiles...")
    build_overview_tiles_from_chunks(config)

    if config.write_debug_masks:
        log.info("Writing debug masks for first chunk only...")
        sample_layers = render_chunk_layers(prepared, config, 0, 0)
        sample_styled = stylize_grid(sample_layers, config)
        sample_final = crop_center_layers(
            sample_styled,
            pad=config.chunk_padding_tiles,
            cell_size=config.tiles_per_cell,
        )
        export_debug_layers(raw_osm, normalized, sample_final, sample_final, config)

    total_elapsed = time.perf_counter() - t0
    log.info("Done.")
    log.info("Output written to: %s", config.output_dir.resolve())
    log.info("Total elapsed: %.1f min", total_elapsed / 60.0)


if __name__ == "__main__":
    main()