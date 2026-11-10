"""Reference catalogues shared by the pipeline (what to load) and the API (how to label)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorSpec:
    code: str
    label: str
    unit: str
    group: str  # "health_system" | "population"


#: World Bank WDI indicators loaded into `health_indicators` (CC BY 4.0).
HEALTH_INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec("SH.MED.BEDS.ZS", "Hospital beds", "per 1,000 people", "health_system"),
    IndicatorSpec("SH.MED.PHYS.ZS", "Physicians", "per 1,000 people", "health_system"),
    IndicatorSpec("SH.MED.NUMW.P3", "Nurses and midwives", "per 1,000 people", "health_system"),
    IndicatorSpec("SH.XPD.CHEX.GD.ZS", "Current health expenditure", "% of GDP",
                  "health_system"),
    IndicatorSpec("SP.POP.65UP.TO.ZS", "Population aged 65+", "% of population", "population"),
)

HEALTH_INDICATOR_BY_CODE = {i.code: i for i in HEALTH_INDICATORS}


#: Forecasting model types (M5) and their display names.
MODEL_LABELS = {
    "seasonal_naive": "Seasonal naive", "last_value": "Last value",
    "moving_average_4": "4-week moving average", "random_forest": "Random Forest",
    "xgboost": "XGBoost",
    # Dengue (D4): the same algorithms with ERA5 weather features added.
    "random_forest_weather": "Random Forest + weather", "xgboost_weather": "XGBoost + weather",
}

#: Forecasting features (pipeline/src/ei_pipeline/forecasting/features.py) for display.
FEATURE_LABELS = {
    "y_lag0": "Positivity this week", "y_lag1": "Positivity 1 week ago",
    "y_lag2": "Positivity 2 weeks ago", "y_lag3": "Positivity 3 weeks ago",
    "y_mean4": "4-week mean positivity", "y_std4": "4-week volatility",
    "y_mean8": "8-week mean positivity", "y_std8": "8-week volatility",
    "y_diff1": "Change over 1 week", "y_diff2": "Change over 2 weeks",
    "y_diff4": "Change over 4 weeks", "y_peak52": "Peak in the last 52 weeks",
    "y_last_year": "Same week last year", "woy_sin": "Time of year (sin)",
    "woy_cos": "Time of year (cos)", "weeks_into_season": "Weeks into the season",
    "log_tests_lag0": "Specimens tested (log)", "tests_trend": "Testing trend",
    "zone_mean_lag0": "Transmission-zone positivity",
    "nbr_mean_lag0": "Neighbouring countries' positivity",
    "nbr_diff2": "Neighbours' 2-week change", "season_nh": "Northern season",
    "season_sh": "Southern season", "season_yr": "Year-round season",
    "lat": "Latitude", "abs_lat": "Distance from equator",
    "log_cases_mean4": "Reported cases, 4-week mean (log)",
}

_WEATHER_VARS = {"temperature": ("Temperature", "mean"), "precipitation": ("Rainfall", "total"),
                 "humidity": ("Humidity", "mean")}


def _weather_labels() -> dict[str, str]:
    out = {}
    for var, (name, agg) in _WEATHER_VARS.items():
        for lag in (4, 8, 12):
            stem = "mean" if agg == "mean" else "sum"
            out[f"{var}_{stem}4_lag{lag}"] = f"{name}, 4-week {agg}, {lag} weeks earlier"
            out[f"{var}_anom4_lag{lag}"] = f"{name} anomaly, {lag} weeks earlier"
    return out


FEATURE_LABELS.update(_weather_labels())


def feature_label(feature: str, target: str = "positivity") -> str:
    """Display label of a forecasting feature for a target ("positivity" or
    "incidence"): the autoregressive features describe the target being forecast."""
    label = FEATURE_LABELS.get(feature, feature)
    if target == "incidence":
        label = (label.replace("Positivity", "Incidence").replace("positivity", "incidence")
                 .replace("Peak in the last", "Peak incidence in the last"))
    return label
