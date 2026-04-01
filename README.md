# Pirchs PZ MMM Rewrite

Ground-up overwrite of the map builder with a different generation flow:

1. Geocode ZIP and build a 20x20 Project Zomboid overview grid.
2. Fetch OSM strictly for nature-only layers.
3. Paint the world with a dark-forest bias:
   - dark grass as the default base
   - medium grass for broader open terrain
   - light grass only for clearly open spaces
4. Generate towns procedurally rather than from OSM.
5. Keep roads orthogonal only.
6. Fetch Waynesborough Country Club separately.
7. Render golf detail from actual golf internals instead of painting the outer property polygon.
8. Place the golf overlay into the densest forest region away from towns, roads, water, and light-grass clearings.
9. Export overview, chunks, masks, and a build manifest.

## Important golf change

The outer `leisure=golf_course` polygon is used only to locate/filter the course data. It is **not** painted as the visible course footprint. The visible golf overlay comes from subfeatures like fairways, greens, tees, bunkers, water, rough, woods, and paths.

## Run

```bash
pip install -r requirements.txt
python main.py
```


## Palette

This rewrite now uses only WorldEd-recognized MAP.png and MAP_veg.png RGB values for terrain and vegetation export.
