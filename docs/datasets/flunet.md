# WHO FluNet

**Status:** verified 2026-11-09 · **Role:** primary source for influenza (MVP)
Coverage numbers: see the generated [flunet_profile.md](flunet_profile.md).

## What it is

FluNet is WHO's global influenza virological surveillance database. National Influenza
Centres and other national laboratories report weekly how many respiratory specimens
they tested and how many were positive for influenza, by type and subtype.

**It does not contain case counts.** Values are laboratory results. The number of
positives depends on how many specimens a country chooses to test, which changes over
time (testing rose sharply after 2020). For that reason the project uses two targets:

- `positives` — lab-confirmed influenza detections per week.
- `positivity` — positives / specimens tested. More comparable across time and
  countries, and the main input for risk thresholds.

## Access

| | |
|---|---|
| Endpoint | `https://xmart-api-public.who.int/FLUMART/VIW_FNT?$format=csv` |
| Auth | None |
| Size | ~32 MB CSV, ~190k rows, 53 columns (Nov 2026) |
| Update frequency | Weekly; recent weeks back-filled as countries report |
| History | 1995 → present (meaningful global coverage from ~2010) |
| Geography | Country / area; ISO3 in `COUNTRY_CODE` |
| Time | `ISO_YEAR`, `ISO_WEEK`, `ISO_WEEKSTARTDATE` (Monday); MMWR weeks also given |
| Grouping | `WHOREGION`, `HEMISPHERE`, `ITZ` (influenza transmission zone) |
| Licence | WHO data policy — free reuse with attribution to WHO FluNet. Confirm wording on the [WHO FluNet page](https://www.who.int/tools/flunet) before public deployment. |

Companion dataset **FluID** (ILI/SARI case counts) is not available through the same
public endpoint (`VIW_FID` returns `NOT_ALLOWED`); out of scope unless another access
route is found.

## Columns used

| Column | Meaning | Use |
|---|---|---|
| `SPEC_PROCESSED_NB` | Specimens tested | Denominator; "reported week" if > 0 |
| `INF_ALL` | All influenza positives | Target (missing in ~44% of rows) |
| `INF_A`, `INF_B` | Positives by type | Fallback for `INF_ALL`; subtype analytics |
| `INF_NEGATIVE` | Negatives | Fallback for specimens tested |
| `ORIGIN_SOURCE` | `SENTINEL`, `NONSENTINEL`, `NOTDEFINED` | De-duplication (below) |

Also present but not used yet: subtype columns (H1N1pdm09, H3, B/Victoria, …), RSV
and other respiratory viruses, `ILI_ACTIVITY` (qualitative 1–4), free-text comments.

## Cleaning rules

Implemented in `pipeline/src/ei_pipeline/sources/flunet.py`.

1. **Exact duplicate rows** are dropped (seen e.g. for Bhutan 2025).
2. **Positives** = `INF_ALL`, else `INF_A + INF_B`. Where all three exist they agree in
   100% of rows.
3. **Specimens tested** = `SPEC_PROCESSED_NB`, else positives + negatives.
4. **Source overlap.** A country can report the same week several times under different
   `ORIGIN_SOURCE` values. `SENTINEL` and `NONSENTINEL` are distinct systems and are
   summed. `NOTDEFINED` rows sometimes repeat one of them (e.g. Austria 2013), so they
   are dropped for any week that also has sentinel/non-sentinel rows.
5. **United Kingdom** is reported as four nations under pseudo-codes `X09` England,
   `X10` Wales, `X11` Northern Ireland, `X12` Scotland. They are summed into `GBR`
   (aliases recorded in `country_code_aliases`). Weeks where only some nations
   reported undercount **positives** for GBR; positivity is less affected. Open item:
   keep nations as sub-regions if an analysis needs it.
6. **Kosovo** uses `XKX`, which is not an ISO 3166 code. `XKX` is the project's
   canonical key; Natural Earth's `KOS` is mapped to it.
7. **Positives > specimens tested** (~1.5k country-weeks): kept, but positivity is left
   empty for those weeks.
8. A week counts as **reported** only if specimens tested > 0. Rows with 0 tests are
   "no surveillance", not "no influenza".

## Loading (`ei ingest flunet`)

Implemented in `pipeline/src/ei_pipeline/ingest/flunet.py`.

- Cleaned rows pass row-level validation (`quality/validation.py`): country code format,
  ISO week range, week start is a Monday and matches the ISO year/week, no future
  weeks, no negative counts. Failing rows are excluded and counted in the run report.
- Rows are upserted into `surveillance_weekly`. When a source revises a past week, the
  previous values are appended to `surveillance_revisions` before the update.
- `is_provisional` is set for weeks after the **reference week** (last week with ≥ 80%
  of the typical number of reporting countries).
- Coverage tiers (A–D, see [profile](flunet_profile.md)) are stored in
  `coverage_profiles` for the reference week.
- Areas FluNet reports that are not yet in `countries` are added without geometry;
  WHO region, hemisphere and transmission zone are taken from FluNet.
- Rows present in the database but no longer in the source are **not deleted**; their
  count is reported (`rows_missing_from_source`).

## Known limitations

- **Reporting delay.** The most recent 2–3 weeks are incomplete (e.g. on 2026-11-09 the
  latest week had 5 reporting countries vs. ~130 normally). Treat them as provisional.
- **Seasonal-only reporting.** Some countries test only during their flu season, which
  creates structural gaps.
- **Testing-volume shifts.** Testing increased several-fold after 2020; raw positives are
  not comparable across eras without normalisation.
- **COVID-19 disruption.** 2020–2021 shows near-absent influenza (2021 global positivity
  ~1%). Models should exclude or flag this period.
- **Sentinel vs. non-sentinel** systems have different populations and biases; summing
  them is a simplification.
- Country-level data cannot support subnational conclusions.
