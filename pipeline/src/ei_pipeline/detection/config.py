"""Detection settings (docs/DESIGN.md §6.3–6.5). Change here, not in code."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: COVID-19 disruption (same window as forecasting): excluded from baselines/thresholds.
COVID_START, COVID_END = date(2020, 3, 1), date(2022, 6, 30)
#: A weekly positivity counts only with at least this many specimens (as in the UI/API).
MIN_TESTS = 10
#: Rows before this are loaded (baselines need 5+ earlier years).
HISTORY_START = date(2010, 1, 4)

# --- Seasons and MEM thresholds -----------------------------------------------------------
NH_START_WEEK = 40
#: MEM needs one epidemic per season: temperate (FluNet NH/SH) countries only.
MEM_SEASON_TYPES = ("NH", "SH")
#: A past season is usable for MEM when this share of its weeks has a valid positivity.
SEASON_MIN_COMPLETENESS = 0.75
#: Fewer usable earlier seasons than this → no thresholds → risk "not assessed".
MIN_SEASONS_FOR_THRESHOLDS = 3
#: Thresholds are stored for seasons starting from this year (history for the season chart).
THRESHOLDS_FROM_YEAR = 2015

# --- Risk ---------------------------------------------------------------------------------
RISK_HORIZON = 2

# --- Anomalies (seasonal baseline + EWMA) -------------------------------------------------
#: Same ISO week ±1 over the latest BASELINE_YEARS usable earlier years.
BASELINE_YEARS = 5
BASELINE_MIN_YEARS = 3
BASELINE_WEEK_HALFWIDTH = 1
UPPER_QUANTILE = 0.90
#: Residual scale floor (percentage points of positivity) so flat baselines don't make
#: every small rise "significant".
RESIDUAL_SCALE_FLOOR_PP = 2.0
EWMA_LAMBDA = 0.3
EWMA_L = 3.0
#: Severity from the standardised residual.
SEVERITY_CUTS = ((5.0, "severe"), (3.0, "high"), (0.0, "moderate"))
#: Anomalies are stored for weeks from this date (history for timelines).
ANOMALIES_FROM = date(2023, 1, 2)

# --- Isolation Forest (secondary, never an alert trigger) ---------------------------------
IFOREST_MIN_WEEKS = 104
IFOREST_CONTAMINATION = 0.02
IFOREST_SEED = 42

# --- Hotspots -----------------------------------------------------------------------------
HOTSPOT_WINDOW_WEEKS = 4
#: Hotspots are computed for every 4-week window ending on or after this week.
HOTSPOTS_FROM = date(2025, 1, 6)
KNN_K = 4
PERMUTATIONS = 999
FDR_ALPHA = 0.05
HOTSPOT_SEED = 12345
WEIGHTS_SPEC = ("queen contiguity (Natural Earth 1:50m) among participating countries; "
                "k=4 nearest by centroid great-circle distance when none; row-standardised")

# --- Per-disease rules (D4) ---------------------------------------------------------------
#: Dengue anomalies run on log(incidence + one case per 100,000 population); a
#: standardised residual of 1 is then a rise of about 28% over the seasonal median.
DENGUE_RESIDUAL_FLOOR = 0.25
#: Dengue MEM seasons are ISO calendar years in every country (one season label per year).
DENGUE_SEASON = "CY"
#: A dengue country joins a hotspot window with incidence in at least this many of its
#: 4 weeks (mean weekly incidence over the reported weeks; gaps are not zeros).
DENGUE_HOTSPOT_MIN_WEEKS = 2


@dataclass(frozen=True)
class DetectionSpec:
    """What differs between diseases. Influenza (M6) runs on test positivity (0–1);
    dengue (D4) on weekly incidence per 100,000."""
    disease: str
    metric: str
    #: Season types MEM is applied to (one epidemic per season).
    mem_season_types: tuple[str, ...]
    #: Seasons overlapping the COVID-19 window are not used; anomaly baselines skip it.
    exclude_covid: bool
    #: "identity" (positivity) or "log" (log(incidence + one case per 100,000)).
    anomaly_scale: str
    #: Floor of the anomaly residual scale, on the anomaly scale.
    residual_floor: float
    #: MEM runs on value × mem_factor (positivity in percent); results are divided back.
    mem_factor: float


INFLUENZA = DetectionSpec(disease="influenza", metric="positivity",
                          mem_season_types=MEM_SEASON_TYPES, exclude_covid=True,
                          anomaly_scale="identity",
                          residual_floor=RESIDUAL_SCALE_FLOOR_PP / 100, mem_factor=100.0)
DENGUE = DetectionSpec(disease="dengue", metric="incidence",
                       mem_season_types=(DENGUE_SEASON,), exclude_covid=False,
                       anomaly_scale="log", residual_floor=DENGUE_RESIDUAL_FLOOR,
                       mem_factor=1.0)
SPECS = {"influenza": INFLUENZA, "dengue": DENGUE}
