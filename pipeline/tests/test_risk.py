"""Risk assessment (M6 rule; test added in M8): forecasts are judged against the MEM
levels of the season that contains the target week."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from ei_pipeline.detection.risk import assess
from ei_pipeline.detection.run import _season_start_of


def test_season_start_by_hemisphere():
    f = _season_start_of(pd.DataFrame({"iso3": ["NNN", "SSS", "YYY"],
                                       "flu_season": ["NH", "SH", None]}))
    # NH seasons start in ISO week 40; a January week belongs to the previous year's season.
    assert f("NNN", date(2025, 1, 13)) == date(2024, 9, 30)
    assert f("NNN", date(2025, 10, 6)) == date(2025, 9, 29)
    assert f("SSS", date(2025, 6, 2)) == date(2024, 12, 30)  # ISO week 1 of 2025
    assert f("YYY", date(2025, 6, 2)) is None and f("ZZZ", date(2025, 6, 2)) is None


def test_assess_levels_and_skips():
    start = date(2024, 9, 30)
    t = SimpleNamespace(season="2024/25", epidemic_threshold=0.10, high=0.30)
    forecasts = pd.DataFrame({
        "id": [1, 2, 3, 4], "iso3": ["AAA", "BBB", "CCC", "DDD"],
        "origin_week": date(2025, 1, 6), "target_week": date(2025, 1, 20),
        "point": [0.05, 0.12, 0.31, 0.5], "lo80": [0.01, None, 0.2, 0.4],
        "hi80": [0.1, None, 0.4, 0.6], "model_type": "xgboost",
    })
    thresholds = {("AAA", start): t, ("BBB", start): t, ("CCC", start): t}
    rows = assess(forecasts, thresholds,
                  lambda iso3, week: None if iso3 == "DDD" else start)
    assert [(r.iso3, r.risk_level) for r in rows] == [
        ("AAA", "low"), ("BBB", "moderate"), ("CCC", "high")]  # DDD: no season, skipped
    assert rows[1].forecast_lo80 is None and rows[0].forecast_lo80 == 0.01
    assert rows[2].rule == ("2-week forecast 31.0% vs 2024/25 MEM epidemic threshold 10.0% "
                            "and high intensity 30.0%")
    assert (rows[0].season, rows[0].high_threshold, rows[0].forecast_id) == ("2024/25", 0.3, 1)
    # A country with a season but no usable thresholds is not assessed either.
    assert assess(forecasts.iloc[[0]], {}, lambda i, w: start) == []
