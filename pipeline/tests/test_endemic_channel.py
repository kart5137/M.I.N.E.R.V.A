"""Endemic channel for dengue risk (D5): year selection, pooled quantiles, the risk rule
with its one-case floor, and the historical check."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from ei_pipeline.detection import config as cfg
from ei_pipeline.detection.channel import (
    channel_check,
    compute_channels,
    week_monday,
    weeks_in,
)
from ei_pipeline.detection.risk import assess_channel, fmt_value, year_ranges

REF = date(2026, 8, 3)


def _weekly(levels: dict[int, float], iso3: str = "AAA", partial: dict[int, int] | None = None
            ) -> pd.DataFrame:
    """Constant incidence per calendar year; `partial` keeps only the first n weeks."""
    rows = []
    for year, v in levels.items():
        n = (partial or {}).get(year, weeks_in(year))
        for w in range(1, n + 1):
            rows.append((iso3, pd.Timestamp(date.fromisocalendar(year, w, 1)), v))
    return pd.DataFrame(rows, columns=["iso3", "week_start", "p"])


def test_week_53_falls_back_to_52():
    assert weeks_in(2020) == 53 and weeks_in(2021) == 52
    assert week_monday(2021, 53) == date.fromisocalendar(2021, 52, 1)


def test_channel_leaves_out_the_highest_year_and_pools_three_weeks():
    # 2019–2025 constant levels; 2024 is the epidemic year.
    weekly = _weekly({2019: 1, 2020: 2, 2021: 3, 2022: 4, 2023: 5, 2024: 100, 2025: 6,
                      2026: 7}, partial={2026: 30})
    rows, reasons = compute_channels(weekly, REF, 2026)
    assert reasons == {}
    r = next(x for x in rows if x.year == 2026 and x.iso_week == 20)
    assert r.years_used == [2019, 2020, 2021, 2022, 2023, 2025]
    assert r.excluded_years == [2024]
    # 6 years x 3 weeks: [1]*3 … [6]*3 → median 3.5, 75th 5, 90th 6 (linear quantiles).
    assert r.n_values == 18
    assert (r.median, r.q75, r.p90) == pytest.approx((3.5, 5.0, 6.0))
    # Channels are stored from CHANNEL_FROM_YEAR on, one row per ISO week.
    assert {x.year for x in rows} == {2024, 2025, 2026}       # 2023: only 4 earlier years
    assert len([x for x in rows if x.year == 2026]) == weeks_in(2026)


def test_incomplete_years_do_not_count_and_too_few_give_a_reason():
    weekly = _weekly({2020: 1, 2021: 2, 2022: 3, 2023: 4, 2024: 5, 2025: 6},
                     partial={2022: 30, 2023: 30})   # 30 of 52 weeks: not usable
    rows, reasons = compute_channels(weekly, REF, 2026)
    assert not [x for x in rows if x.year == 2026]
    assert reasons["AAA"].startswith("4 complete reporting years in 2019–2025")
    assert "needs 5" in reasons["AAA"]


def test_risk_against_the_channel_with_a_one_case_floor():
    weekly = _weekly({y: 1.0 + (y % 3) for y in range(2018, 2026)})
    rows, _ = compute_channels(weekly, REF, 2026)
    ch = {(r.iso3, r.week_start): r for r in rows}
    target = date(2026, 8, 17)
    c = ch[("AAA", target)]
    fc = pd.DataFrame({
        "id": [1, 2, 3], "iso3": ["AAA"] * 3, "origin_week": [REF] * 3,
        "target_week": [target] * 3, "point": [c.q75 - 0.01, c.q75, c.p90 + 0.5],
        "lo80": [np.nan] * 3, "hi80": [np.nan] * 3, "model_type": ["xgboost"] * 3})
    out = assess_channel(fc, ch, {"AAA": 0.001})
    assert [r.risk_level for r in out] == ["low", "moderate", "high"]
    assert out[0].method == "endemic_channel" and out[0].season == "2026"
    assert out[0].epidemic_threshold == c.q75 and out[0].high_threshold == c.p90
    assert "week 34 from 2019–2020, 2022–2025 (highest year 2021 left out)" in out[0].rule
    # A country that usually reports zero: the levels rise to one weekly case.
    zero = _weekly({y: 0.0 for y in range(2018, 2026)}, iso3="ZZZ")
    zrows, _ = compute_channels(zero, REF, 2026)
    zch = {(r.iso3, r.week_start): r for r in zrows}
    fz = fc.assign(iso3="ZZZ", point=[0.05, 0.2, 0.0])
    got = assess_channel(fz, zch, {"ZZZ": 0.1})
    assert [r.risk_level for r in got] == ["low", "high", "low"]
    assert got[0].epidemic_threshold == 0.1


def test_channel_check_counts_weeks_above_the_channel():
    weekly = _weekly({2016: 1, 2017: 2, 2018: 3, 2019: 4, 2020: 5, 2021: 6, 2022: 7,
                      2023: 50, 2024: 1, 2025: 4})
    rows, _ = compute_channels(weekly, REF, 2026)
    check = channel_check(weekly, rows, REF)
    assert set(check) == {"2023", "2024", "2025"}          # 2026 is not complete
    assert check["2023"]["above_channel"] == 1.0           # an epidemic year: every week
    assert check["2024"]["above_channel"] == 0.0
    assert check["2023"]["countries"] == 1


def test_wording_helpers():
    assert year_ranges([2019, 2020, 2021, 2023, 2025]) == "2019–2021, 2023, 2025"
    assert year_ranges([2024]) == "2024"
    assert fmt_value(0.003, "incidence") == "< 0.01 per 100k"
    assert fmt_value(0.0, "incidence") == "0.00 per 100k"
    assert fmt_value(12.34, "incidence") == "12.3 per 100k"


def test_dengue_spec_uses_the_channel_and_influenza_mem():
    assert cfg.DENGUE.risk_method == "endemic_channel"
    assert cfg.INFLUENZA.risk_method == "mem"
    assert timedelta(weeks=cfg.RISK_HORIZON) == timedelta(days=14)
