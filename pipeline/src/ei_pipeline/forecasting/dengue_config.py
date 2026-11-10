"""Dengue forecasting settings (D4). Shared settings (horizons, backtest start, origin
step, refit interval, conformal levels, hyperparameters) are in `config.py`."""

from __future__ import annotations

from ei_pipeline import weather

TARGET = "incidence"
#: Dengue coverage tiers modelled; weekly reporters only (monthly series are not split).
ELIGIBLE_TIERS: tuple[str, ...] = ("A", "B")
#: Floor of the 8-week volatility scale on the log(incidence + one case per 100,000)
#: scale (0.10 ≈ a 10% change).
SCALE_FLOOR = 0.10
#: Mondrian conformal groups by reported cases per week (4-week mean at the origin):
#: small counts are noisy, so they get their own (wider) quantiles.
CONFORMAL_GROUP_EDGES = (10, 100, 1000)

#: Weather features: 4-week windows ending 4, 8 and 12 weeks before the origin
#: (weather.lagged_features), as values and as anomalies from the country's 2013–2022
#: normal for the same weeks of the year.
WEATHER_WINDOW = weather.FEATURE_WINDOW
WEATHER_LAGS = weather.FEATURE_LAGS
NORMAL_YEARS = (2013, 2022)
