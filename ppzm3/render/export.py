from PIL import Image

from ppzm3.config import AppConfig
from ppzm3.types import RasterLayers


def _build_base_image(final_grid: RasterLayers, config: AppConfig) -> Image.Image:
    width = config.tiles_per_cell
    height = config.tiles_per_cell

    image = Image.new("RGB", (width, height), (90, 100, 35))
    pixels = image.load()

    for y in range(height):
        for x in range(width):
            if final_grid.road[y][x]:
                color = (100, 100, 100)        # Road wins over water
            elif final_grid.water[y][x]:
                color = (0, 138, 255)
            elif final_grid.building[y][x]:
                color = (120, 70, 20)
            elif final_grid.golf[y][x]:
                color = (145, 135, 60)         # Light grass for golf course ground
            elif final_grid.farmland[y][x]:
                color = (145, 135, 60)
            elif final_grid.forest[y][x]:
                color = (90, 100, 35)
            elif final_grid.residential[y][x]:
                color = (117, 117, 47)
            else:
                color = (90, 100, 35)

            pixels[x, y] = color

    return image


def _build_veg_image(final_grid: RasterLayers, config: AppConfig) -> Image.Image:
    width = config.tiles_per_cell
    height = config.tiles_per_cell

    image = Image.new("RGB", (width, height), (0, 255, 0))  # default = light long grass
    pixels = image.load()

    for y in range(height):
        for x in range(width):
            if (
                final_grid.road[y][x]
                or final_grid.building[y][x]
                or final_grid.water[y][x]
                or final_grid.golf[y][x]
            ):
                color = (0, 0, 0)              # no vegetation
            elif final_grid.forest[y][x]:
                color = (255, 0, 0)            # dense forest
            elif final_grid.farmland[y][x]:
                color = (255, 128, 0)          # dead corn 1
            elif final_grid.residential[y][x]:
                color = (0, 128, 0)            # mainly grass, some trees
            else:
                color = (0, 255, 0)            # light long grass

            pixels[x, y] = color

    return image


def save_chunk_pair(final_chunk: RasterLayers, config: AppConfig, cell_x: int, cell_y: int) -> None:
    chunks_dir = config.output_dir / f"{config.map_name}_chunks"
    row_dir = chunks_dir / f"{cell_y:02d}"
    row_dir.mkdir(parents=True, exist_ok=True)

    base_image = _build_base_image(final_chunk, config)
    veg_image = _build_veg_image(final_chunk, config)

    base_name = f"{cell_y:02d}_{cell_x:02d}.png"
    veg_name = f"{cell_y:02d}_{cell_x:02d}_veg.png"

    base_image.save(row_dir / base_name, format="PNG")
    veg_image.save(row_dir / veg_name, format="PNG")


def build_overview_tiles_from_chunks(config: AppConfig) -> None:
    chunks_dir = config.output_dir / f"{config.map_name}_chunks"
    overview_dir = config.output_dir / f"{config.map_name}_overview"
    overview_dir.mkdir(parents=True, exist_ok=True)

    block = config.overview_block_cells
    cell_size = config.tiles_per_cell

    block_rows = (config.cells_y + block - 1) // block
    block_cols = (config.cells_x + block - 1) // block

    for by in range(block_rows):
        for bx in range(block_cols):
            start_y = by * block
            start_x = bx * block
            end_y = min(start_y + block, config.cells_y)
            end_x = min(start_x + block, config.cells_x)

            cells_w = end_x - start_x
            cells_h = end_y - start_y

            overview = Image.new("RGB", (cells_w * cell_size, cells_h * cell_size), (0, 0, 0))

            for cy in range(start_y, end_y):
                row_dir = chunks_dir / f"{cy:02d}"
                for cx in range(start_x, end_x):
                    chunk_path = row_dir / f"{cy:02d}_{cx:02d}.png"
                    if not chunk_path.exists():
                        continue

                    chunk = Image.open(chunk_path)
                    paste_x = (cx - start_x) * cell_size
                    paste_y = (cy - start_y) * cell_size
                    overview.paste(chunk, (paste_x, paste_y))

            overview_name = f"base_overview_r{by:02d}_c{bx:02d}.png"
            overview.save(overview_dir / overview_name, format="PNG")