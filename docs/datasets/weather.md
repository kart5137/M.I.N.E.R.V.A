# Weather: ERA5 via Open-Meteo

**Status:** verified 2026-11-10 · **Role:** weather context for dengue (post-MVP phase P1,
milestone D3) and forecasting features of the dengue `*_weather` models (D4).

## What it is

ERA5 is ECMWF's global reanalysis (Copernicus Climate Change Service): one model run
consistently from 1940 to about five days ago, on a ~0.25° (~25 km) grid. Open-Meteo's
Historical Weather API serves it per point as daily values. We request `models=era5`
explicitly: the API's default "best match" blends higher-resolution forecast models into
recent days, which shifted a Brazil test point by 0.7 °C and 6 humidity points in
Sep–Oct 2026 and would put a break into the series.

| | |
|---|---|
| Endpoint | `https://archive-api.open-meteo.com/v1/archive?models=era5&timezone=auto` |
| Variables | `temperature_2m_mean` (°C), `precipitation_sum` (mm), `relative_humidity_2m_mean` (%) |
| Days | Local time zone of the point (`timezone=auto`) |
| Latency | ~5 days; the latest days are preliminary (ERA5T) and may be revised |
| Licence | Open-Meteo data CC BY 4.0; ERA5 under the Copernicus licence (attribution). The free API is for **non-commercial use** |
| Limits | Weighted calls: a request counts max(1, days ÷ 14) (≤ 10 variables). 600 / minute, 5,000 / hour, 10,000 / day per IP |

## Point per country

One representative point per area (DENGUE_PLAN §2.4), stored in `weather_points`:

- the Natural Earth **label point** (`countries.centroid`) for 191 areas;
- the **main town** for the 8 reporting areas without a boundary (Bonaire, Guadeloupe,
  French Guiana, Madeira, Martinique, Mayotte, Réunion, Tokelau) — coordinates in
  `pipeline/src/ei_pipeline/ingest/weather.py`.

Weather is loaded for every area with a WHO dengue report (199).

## Processing (`ei ingest weather`)

`pipeline/src/ei_pipeline/weather.py` and `ingest/weather.py`:

1. **Daily checks.** Values outside −60…60 °C, 0…500 mm/day or 0…100 % are treated as
   missing and counted; missing days are counted.
2. **ISO weeks** (Monday–Sunday, as for surveillance): mean temperature, total
   precipitation, mean humidity. A week is stored **only when all 7 days have all three
   values**; incomplete weeks (the current week, rare gaps) are dropped and counted, never
   filled.
3. **Upsert** into `weather_weekly` (unchanged weeks untouched; revised values updated in
   place — weather is a model output, so no revision history is kept).
4. **Normals** for the dashboard are computed by the API: the mean of the same ISO week
   over 2013–2022 (week 53 uses week 52).
5. **Features for D4** (`weather.lagged_features`): 4-week mean temperature and humidity
   and 4-week total precipitation, lagged 4, 8 and 12 weeks; missing weeks stay gaps.
   `forecasting/data.py` adds each one's anomaly from the country's 2013–2022 mean for the
   same ISO week (18 features in all).

## Loading within the free quota

The history from 2013 is ~360 weighted calls per area, ~72,000 in total — about seven
days of the free daily limit. Loading is therefore **resumable**:

- each run continues every area from its last stored week, **forecast-ready areas first**
  (dengue tier A/B, 52 areas, ~2 days), then the rest;
- requests are paced client-side below the minute and hour limits (500 / 4,500) and a run
  stops cleanly at its **budget** (`--budget`, default 4,400), its time limit
  (`--max-minutes`; 30 in the workflow) or when the API reports the hourly/daily limit;
  requests time out after 30 s and are retried (from GitHub's runners some hang); what arrived is stored, and the run is recorded as succeeded with
  `stopped_early` in its quality report;
- `.github/workflows/weather.yml` runs `ei ingest weather --backfill-only` twice a day
  (separate hourly windows). When every area is complete it makes no requests;
- once complete, the weekly job (`ei weekly`) re-fetches each area's last **8 weeks**
  (ERA5T revisions). Weather is optional in the weekly job: a failure is logged and the
  job continues; dengue forecasting then uses the weather already stored (the newest
  weeks lack weather features, which the tree models handle as missing).

GitHub-hosted runners share IP addresses, so other users can use up the per-IP quota and
a run may stop early; the next run continues.

## Why not NASA POWER (evaluated and rejected, 2026-11-10)

NASA POWER (MERRA-2 / GEOS-IT, 0.5°) was tried first because it has no weighted quota (the
whole history loads in about a minute). After loading it for all 199 areas, it was compared
with ERA5 at 24 country points, weekly, for 2015–16 and 2024–25
([data](../../data/profiles/weather_nasa_vs_era5.csv)):

- Median agreement is similar in both periods (correlation of weekly values: temperature
  0.93–0.94, precipitation 0.74–0.76, humidity 0.85), **but NASA drifts in some areas**:
  for Brazil, NASA − ERA5 rose from +0.3 °C / −1.9 humidity points (2013) to +2.6 °C /
  −15.8 points (2026), while ERA5's own Brazil series stays flat.
- **Broken points:** Singapore's precipitation rose from ~2,000 mm/year (2013–2020) to
  32,635 mm in Jan–Oct 2026 (ERA5: 1,627 mm); Senegal has a 785 mm week (July 2025).
- The drift falls in D4's backtest period (from October 2024), so it would bias the
  with/without-weather comparison.

ERA5 is one consistent model through time, so it was chosen despite the quota (decision
recorded with the user, 2026-11-10).

## Known limitations

- **One point per country.** Large or climatically varied countries (Brazil, India,
  Indonesia, Peru) are represented by a single location, often not where dengue
  transmission occurs; a population-weighted or sub-national approach would be better.
- **Reanalysis, not observations.** ERA5 precipitation in particular differs from gauges,
  most in the tropics and in mountains.
- **Small islands** may fall in grid cells dominated by sea.
- **Free API, non-commercial terms.** A commercial deployment would need an Open-Meteo plan
  or direct ERA5 access (Copernicus Climate Data Store).
