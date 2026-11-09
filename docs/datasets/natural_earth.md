# Natural Earth — Admin 0 Countries (1:50m)

**Status:** verified and ingested 2026-11-09 · **Role:** country boundaries and label points

| | |
|---|---|
| Version | v5.1.2 (`nvkelso/natural-earth-vector` tag) |
| File | `geojson/ne_50m_admin_0_countries.geojson` (~3 MB, 242 features) |
| Licence | Public domain |
| Loaded into | `countries.geom` (MultiPolygon, EPSG:4326), `countries.centroid` (label point) |
| Job | `ei ingest boundaries` → `pipeline/src/ei_pipeline/ingest/boundaries.py` |

## Code handling

- Key: `ISO_A3_EH` (`ISO_A3` is `-99` for France and Norway). Where `ISO_A3_EH` is
  also `-99`, `ADM0_A3` is used: Kosovo (`KOS`), N. Cyprus (`CYN`), Somaliland (`SOL`),
  Siachen Glacier (`KAS`).
- Kosovo is stored as **`XKX`** (the code used by WHO FluNet and the World Bank);
  `KOS` is recorded in `country_code_aliases`.
- Features sharing a code are unioned: Australia (`AUS`) has 3 features in 1:50m
  (mainland plus external territories). Name and label point come from the main feature.
- Invalid geometries are repaired with `ST_MakeValid` (count recorded per run).
- The label point (`LABEL_X/Y`) is used as the centroid: it is chosen by Natural Earth
  to fall inside the main landmass, unlike a geometric centroid.

## Known limitations

- **Overseas departments are part of their parent country.** Guadeloupe, French Guiana
  and Martinique report to FluNet separately but are drawn inside France's geometry.
  They exist in `countries` without geometry and are therefore not drawn on the map;
  France's polygon must not be coloured with their values.
- FluNet's historical `SCG` (Serbia and Montenegro, 2003–2006) has no boundary.
- Disputed areas follow Natural Earth's de facto conventions; this project takes no
  position on them.
- The API serves boundaries simplified with `ST_SimplifyPreserveTopology` (0.01°),
  suitable for display only.
