# Pirchs PZ MMM

<div align="center">

# Pirchs PZ MMM
### Project Zomboid map generation pipeline powered by OpenStreetMap

> A Python-based pipeline that geocodes a target ZIP code, pulls OpenStreetMap data, normalizes it into semantic layers, rasterizes those layers into tile grids, applies gameplay-oriented cleanup/stylization, and exports chunk PNGs for Project Zomboid map prototyping.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Status](https://img.shields.io/badge/Status-Prototype-orange?style=for-the-badge)
![Data](https://img.shields.io/badge/Data-OpenStreetMap-7EBC6F?style=for-the-badge)
![Render](https://img.shields.io/badge/Output-Chunked%20PNGs-6C63FF?style=for-the-badge)

</div>

---

## Table of Contents

- [What This Project Is](#what-this-project-is)
- [What Problem It Solves](#what-problem-it-solves)
- [Current Pipeline](#current-pipeline)
- [Repository Layout](#repository-layout)
- [How the Code Works](#how-the-code-works)
  - [Entry Point](#entry-point)
  - [Configuration](#configuration)
  - [Fetch Layer](#fetch-layer)
  - [Normalization Layer](#normalization-layer)
  - [Rasterization Layer](#rasterization-layer)
  - [Stylization Layer](#stylization-layer)
  - [Render and Export Layer](#render-and-export-layer)
  - [Data Types](#data-types)
- [Default Runtime Behavior](#default-runtime-behavior)
- [Installation](#installation)
- [Running the Project](#running-the-project)
- [Output Files](#output-files)
- [Caching Behavior](#caching-behavior)
- [Why the Pipeline Is Structured This Way](#why-the-pipeline-is-structured-this-way)
- [Known Current Limitations](#known-current-limitations)
- [Recommended Next Improvements](#recommended-next-improvements)
- [Maintainer Notes](#maintainer-notes)
- [Git Workflow](#git-workflow)

---

## What This Project Is

**Pirchs PZ MMM** is a Python project for turning real-world map data into a **Project Zomboid-friendly prototype map representation**.

Today, the codebase already does the important hard parts:

1. geocodes a ZIP code into a center point
2. builds a bounding box sized from your map dimensions
3. queries OpenStreetMap through Overpass
4. normalizes roads, water, landuse, and buildings into internal layers
5. converts lat/lon coordinates into a global raster grid
6. renders chunk-local masks with padding
7. applies a cleanup/stylization pass so the result feels more game-like
8. exports chunk PNGs and overview images

This is not just a downloader or a one-off script. It is already a **multi-stage generation pipeline**.

---

## What Problem It Solves

Raw OSM data is useful, but it is not directly playable.

Real map data has problems for a game workflow:
- roads may overlap water in ugly ways
- buildings can look noisy or isolated
- landuse shapes are too literal
- residential areas need stronger interpretation
- golf courses need special handling
- large maps need chunk-based rendering instead of drawing everything all at once

This project exists to bridge that gap.

The core idea is:

```text
real-world geographic data -> normalized semantic layers -> stylized gameplay-oriented raster output
```

That design choice is visible throughout the codebase.

---

## Current Pipeline

```text
ZIP Code / Config
        |
        v
Nominatim geocoding
        |
        v
Center point + derived bounding box
        |
        v
Overpass API query
        |
        v
Raw OSM payload cache
        |
        v
Normalization
  - roads
  - water
  - landuse
  - buildings
        |
        v
Global coordinate conversion
        |
        v
Per-cell feature indexing
        |
        v
Chunk raster rendering with padding
        |
        v
Stylization / cleanup pass
        |
        v
Crop center cell
        |
        v
Export base tile + vegetation tile
        |
        v
Build overview images
```

---

## Repository Layout

Based on the code you shared, the project currently looks like this:

```text
pirchs-pz-mmm/
|
|-- main.py
|-- requirements.txt
|-- .gitignore
|
`-- ppzm3/
    |-- config.py
    |-- types.py
    |
    |-- core/
    |   |-- normalize.py
    |   |-- rasterize.py
    |   `-- stylize.py
    |
    |-- fetch/
    |   |-- geocode.py
    |   `-- osm.py
    |
    `-- render/
        |-- debug.py
        `-- export.py
```

That is already a solid layout. It cleanly separates:
- configuration
- fetching external data
- normalization
- rasterization
- stylization
- export

---

## How the Code Works

## Entry Point

The current entry point is `main.py`.

The `main()` function sets up logging, builds the default config, ensures cache/output directories exist, geocodes the ZIP code, derives the bounding box, fetches OSM data, normalizes it, prepares render data, then loops through every map cell to render, stylize, crop, and save chunk pairs. After chunk export, it also builds overview tiles.

That means the full job flow is centralized and easy to follow:
- configure
- fetch
- normalize
- prepare
- render each chunk
- stylize each chunk
- save outputs
- build overview images

This is a good structure for maintainability because the orchestration is in one place while the heavy logic lives in module-specific files.

---

## Configuration

The configuration object is `AppConfig`, defined as a dataclass.

It currently stores:
- map metadata (`map_name`, `zip_code`, `country_code`)
- world sizing (`cells_x`, `cells_y`, `tiles_per_cell`)
- resolved geographic data (`center_lat`, `center_lon`, `bbox`)
- paths (`cache_dir`, `output_dir`)
- service endpoints (`overpass_url`, `nominatim_url`, `user_agent`)
- road width rules
- chunk padding
- overview block size
- logging frequency
- optional debug mask writing

The `default()` constructor gives the project a runnable baseline configuration. Out of the box, the default map name is `ppzm3_19010_50x40`, ZIP is `19010`, dimensions are `50 x 40`, and each cell is `300` tiles wide/high.

Two computed properties are especially useful:
- `grid_width`
- `grid_height`

These derive the full raster resolution from the number of cells and tiles per cell, which the rest of the pipeline relies on.

### Why this matters
By centralizing map size, endpoints, and styling knobs in one config object, the rest of the code stays much cleaner. Every stage receives the same shared state instead of manually recomputing dimensions or hardcoding values in multiple places.

---

## Fetch Layer

The fetch layer is split into two responsibilities:

### 1. Geocoding (`fetch/geocode.py`)
This module converts a ZIP code into a center latitude/longitude using Nominatim.

Key behavior:
- caches geocode responses to `cache/zip_<country>_<zip>.json`
- supports force refresh
- computes miles-per-degree helpers
- converts the center point into a bounding box sized to your configured map dimensions

The bounding box size is not arbitrary. It is derived from:
- `cells_x`
- `cells_y`
- `tiles_per_cell`

That means your requested game map dimensions directly determine how much real-world geography gets pulled.

### 2. OSM fetch (`fetch/osm.py`)
This module builds an Overpass query using the bounding box and requests:
- roads via `highway`
- waterways
- natural water
- landuse
- natural wood
- buildings

It also includes a fallback list of Overpass endpoints instead of relying on a single server. That is a very good practical choice for a prototype, because public Overpass services are often overloaded.

Key behavior:
- writes raw OSM JSON into cache
- tries multiple endpoints in order
- reports failures clearly
- explains likely causes when every endpoint fails

### Why this matters
This fetch split is the correct one:
- geocoding is about where the map is
- OSM fetching is about what exists inside the map

Keeping those separate makes the code easier to reason about and easier to replace later.

---

## Normalization Layer

The normalization stage takes raw OSM elements and converts them into a consistent internal structure.

This layer does three important things:

### 1. Indexes nodes
OSM ways reference node IDs. The code first builds a node lookup table so ways can be expanded into actual coordinate sequences.

### 2. Reconstructs way coordinates
Each way becomes a list of `(lat, lon)` coordinate pairs.

### 3. Classifies features into semantic buckets
The code currently groups data into:
- `roads`
- `water`
- `landuse`
- `buildings`

Landuse classification includes special handling:
- `leisure=golf_course` -> `golf`
- `landuse=*` -> the raw landuse kind
- `natural=*` -> natural kind
- `leisure=park` -> `park`

That special-case handling is important because golf courses and parks have gameplay implications later in the raster and stylization stages.

The normalized output is represented by `NormalizedLayers`, which stores:
- `roads`
- `water`
- `landuse`
- `buildings`

### Why this matters
Normalization is the seam between “messy real-world source data” and “pipeline-friendly internal data.” Once features are normalized, later stages do not need to understand OSM node/way internals anymore.

---

## Rasterization Layer

The rasterization layer is where geographic coordinates become game-grid coordinates.

This is implemented in `core/rasterize.py`, and it is one of the strongest parts of the current project.

### Global coordinate conversion
The `_latlon_to_global()` function converts lat/lon points into integer positions in the full map grid using the configured bounding box and total raster dimensions.

### Feature bounds
Each feature is given bounding coordinates so later code can cheaply test whether it matters for a chunk.

### Per-cell indexing
The project builds indexes of which features intersect which cells. That means the renderer does not have to scan every road, water feature, landuse polygon, and building for every single chunk.

Instead, it can ask:
> what features are likely relevant to cell `(x, y)` and its neighbors?

That is a very good scaling decision.

### Chunk rendering with padding
For each cell:
- a padded local raster area is created
- candidate roads, water, landuse, and buildings are drawn into masks
- roads are lines with widths controlled by `config.road_widths`
- water can be polygon-filled if closed, otherwise line-drawn
- landuse is split into forest, farmland, residential, and golf masks
- buildings are polygon-filled

Padding matters because it prevents hard seams during post-processing. The chunk is rendered slightly larger than the final cell, then cropped back to the center afterward.

### Why this matters
This stage is the transition from semantic vector data into chunk-friendly bitmap layers. By indexing features first and rasterizing per chunk, the project is much more practical for larger maps than a naive full-map redraw approach.

---

## Stylization Layer

The stylization layer is where the project stops being a literal OSM renderer and starts becoming a **game map generator**.

This is implemented in `core/stylize.py`.

The file includes a full set of grid operations:
- clone
- dilate
- erode
- open
- close
- subtract
- and/or
- neighbor counting
- isolated pixel cleanup
- small component removal

Those building blocks are then combined into gameplay-oriented cleanup rules.

### Current stylization logic includes:

#### Road cleanup
- closes road gaps
- removes tiny road fragments
- removes weak road-over-water overlaps unless they behave more like bridges
- carves roads out of building buffers

#### Water cleanup
- closes water shapes to reduce fragmentation

#### Building cleanup
- closes buildings
- removes small components
- removes isolated pixels
- removes buildings on water
- removes building overlap with golf

#### Golf cleanup
- closes golf masks
- removes tiny golf fragments
- subtracts water and buildings from golf

#### Residential inflation
Residential area is expanded outward from buildings, but only near roads. This is a smart heuristic because it turns individual building detections into broader playable residential zones.

#### Farmland shaping
Farmland is eroded/opened, then carved away from:
- roads
- water
- residential zones
- golf

#### Forest shaping
Forest is closed/opened, then carved away from:
- roads
- water
- residential zones
- golf

Finally, the layer conflicts are resolved so that:
- building wins over surrounding land classes
- residential is removed from buildings
- farmland and forest are removed from buildings
- farmland and forest are also removed from residential
- tiny leftover components are deleted

### Why this matters
This file is the clearest statement of your design philosophy:

```text
OSM is the input, not the final truth.
```

You are already interpreting reality into something closer to how a Zomboid map should play.

---

## Render and Export Layer

The render/export code turns processed raster layers into visible PNG output.

### Base image generation
The base chunk image uses a color hierarchy:
- roads
- water
- buildings
- golf
- farmland
- forest
- residential
- default terrain

Roads are intentionally allowed to win over water in the base image, reflecting your stated goal that road crossings over water should behave more like bridges than water simply overwriting roads.

### Vegetation image generation
The vegetation image uses encoded colors for biome/vegetation behavior:
- roads/buildings/water/golf -> no vegetation
- forest -> dense forest
- farmland -> dead corn style
- residential -> mostly grass / some trees
- default -> light long grass

### Chunk pair export
Each cell exports:
- a base PNG
- a `_veg.png` companion image

These are stored by row folder, which keeps large output sets more organized.

### Overview image generation
The exporter can also stitch multiple chunk images into block-based overview images. This is useful for sanity-checking larger maps without opening hundreds or thousands of individual cell files.

### Debug masks
There is also a debug export path that can write layer masks for:
- roads
- water
- forest
- farmland
- building
- residential
- golf

That is a strong maintainability feature because it makes tuning much easier.

---

## Data Types

The shared type layer includes:
- `BBox`
- `NormalizedLayers`
- `RasterLayers`

### `BBox`
Stores:
- south
- west
- north
- east

It also provides an Overpass-friendly tuple conversion.

### `NormalizedLayers`
Stores the normalized vector-like semantic buckets:
- roads
- water
- landuse
- buildings

### `RasterLayers`
Stores the raster masks used during rendering/stylization:
- road
- water
- forest
- farmland
- building
- residential
- golf

These types make the pipeline easier to understand because each stage has a clear data contract.

---

## Default Runtime Behavior

With the current default configuration, the project is set up to generate a map using:
- ZIP code `19010`
- country `us`
- map size `50 x 40` cells
- `300` tiles per cell

The pipeline:
1. geocodes the ZIP code
2. derives the bounding box from the requested map size
3. fetches OSM data
4. caches the raw results
5. normalizes and prepares feature data
6. renders every chunk
7. stylizes every chunk
8. exports chunk pairs
9. builds overview tiles
10. optionally writes debug masks when enabled

It also logs progress:
- startup settings
- chunk throughput
- ETA
- row completion timing
- final output location

That makes long render jobs easier to watch.

---

## Installation

## Requirements
You currently depend on:
- `requests>=2.31.0`
- `numpy>=1.26.0`
- `pillow>=10.0.0`

### 1. Create a virtual environment

On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

---

## Running the Project

From the project root:

```powershell
python main.py
```

That will run the full pipeline using the defaults in `AppConfig.default()`.

If you want a different target ZIP or map size right now, the current code expects you to edit the default config values in `ppzm3/config.py`.

---

## Output Files

The project writes into:
- `cache/`
- `output/`

### Cache contents
Examples:
- geocode response cache
- raw OSM payload cache

### Output contents
Examples:
- `<map_name>_chunks/`
- `<map_name>_overview/`
- optional debug mask PNGs

Per chunk, the exporter writes:
- `YY_XX.png`
- `YY_XX_veg.png`

That separation between base and vegetation output is a good fit for later tooling or conversion stages.

---

## Caching Behavior

The project already has a practical caching strategy:
- ZIP geocode responses are cached
- raw OSM payloads are cached

This matters a lot because:
- Overpass is rate-limited and often overloaded
- geocoding does not need to be repeated every run
- iterative tuning is much faster when fetches are cached

For map generation work, this is exactly the kind of quality-of-life feature that saves a lot of time.

---

## Why the Pipeline Is Structured This Way

The current structure is a strong choice for this kind of project.

### Fetch -> Normalize -> Rasterize -> Stylize -> Export
This chain is good because each stage has one job:

- **Fetch** gets source data
- **Normalize** makes source data internally consistent
- **Rasterize** converts geometry into tile space
- **Stylize** applies gameplay rules
- **Export** writes images for inspection and downstream use

That separation is why the code already feels like a project instead of a pile of scripts.

### Chunk-first rendering
Rendering one chunk at a time with padding is also the right decision for scalability and seam control.

### Semantic intermediate layers
Instead of drawing directly from OSM into final colors, the code carries semantic masks like:
- road
- water
- building
- residential
- farmland
- forest
- golf

That gives you room to keep improving gameplay logic without rewriting the whole renderer.

---

## Known Current Limitations

This repo is already promising, but it is still early-stage.

### Current limitations that are visible from the code
- configuration is still hardcoded in `AppConfig.default()`
- the runtime is script-driven rather than CLI-driven
- OSM coverage is intentionally limited to the queried tags
- styling rules are heuristic and still being tuned
- output is PNG-based rather than direct WorldEd/project export
- road hierarchy is width-based rather than full network-aware planning
- bridge handling is heuristic rather than explicit
- vegetation/base rendering is prototype-oriented rather than final-game-accurate

These are not failures. They are normal prototype-stage tradeoffs.

---

## Recommended Next Improvements

The most valuable next steps would probably be:

### 1. Add CLI arguments
Support things like:
- `--zip`
- `--country`
- `--cells-x`
- `--cells-y`
- `--tiles-per-cell`
- `--force-refresh`

That would remove the need to edit config defaults for every run.

### 2. Add a config file format
A TOML or YAML config would make map presets much easier.

### 3. Improve road-aware land generation
A future version could let major roads drive:
- denser settlement corridors
- stronger town shapes
- better bridge handling
- more believable rural vs suburban transitions

### 4. Add export toward WorldEd-friendly workflows
That would help turn prototypes into actual PZ map production assets.

### 5. Add tests for geometry and grid transforms
Especially:
- bounding box logic
- lat/lon mapping
- chunk crop correctness
- stylize operations

### 6. Add optional preview tooling
A simple overview viewer or HTML preview would speed iteration.

---

## Maintainer Notes

If a new maintainer comes into this repo, the mental model should be:

- `main.py` orchestrates the job
- `config.py` defines map shape and runtime settings
- `fetch/*` pulls external data
- `core/normalize.py` converts OSM into internal semantic layers
- `core/rasterize.py` turns those layers into chunk raster masks
- `core/stylize.py` makes the result more playable and less literal
- `render/export.py` and `render/debug.py` write output files

The most important conceptual distinction in this codebase is:

```text
The project is not trying to copy OSM exactly.
It is trying to reinterpret OSM into something usable for a Project Zomboid map workflow.
```

That should stay true as the project evolves.

---

## Git Workflow

## README filename
Use:

```text
README.md
```

That exact capitalization is the normal GitHub standard.

## Suggested `.gitignore`
Because you specifically want to keep generated and environment folders out of the repo, your `.gitignore` should include at minimum:

```gitignore
.venv/
cache/
output/
__pycache__/
*.pyc
```

A fuller version is fine too, but those are the important ones for this project.

## First commit from the project root

From:

```text
C:\Users\ryanj\Development\GameProjects\ZomboidMapping\pirchs-pz-mmm
```

run:

```powershell
git status
git add .gitignore
git add README.md
git add .
git commit -m "initial commit: add OSM map generator pipeline"
```

If you want to be a little more explicit and avoid relying on `git add .`, use:

```powershell
git add main.py
git add requirements.txt
git add .gitignore
git add README.md
git add ppzm3
git commit -m "initial commit: add OSM map generator pipeline"
```

## If you have not added the GitHub remote yet

```powershell
git remote add origin https://github.com/YOUR_USERNAME/pirchs-pz-mmm.git
git branch -M main
git push -u origin main
```

## If the remote already exists
Just push:

```powershell
git branch -M main
git push -u origin main
```

---

<div align="center">

### Pirchs PZ MMM
**Detailed README generated from the current project structure and code shared in this chat**

</div>
