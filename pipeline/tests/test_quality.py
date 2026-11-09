from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from conftest import make_raw
from ei_pipeline.quality.coverage import analyse, assign_tier, longest_run, reference_week
from ei_pipeline.quality.validation import validate_weekly
from ei_pipeline.sources.flunet import clean


def test_reference_week_excludes_lagging_weeks():
    weekly, _ = clean(make_raw(weeks=40, countries=("ARG", "BRA", "CHL"), drop_last=2))
    ref, provisional = reference_week(weekly)
    last = weekly["week_start"].max()
    # Only ARG reports the last two weeks → 1 of 3 countries < 80% of typical.
    assert ref == last - pd.Timedelta(weeks=2)
    assert list(provisional.values) == [1, 1]


def test_longest_run():
    flags = pd.Series([True, False, False, True, False, False, False])
    assert longest_run(flags, False) == 3 and longest_run(flags, True) == 1


@pytest.mark.parametrize(("row", "tier"), [
    ({"window_weeks_reported": 0}, "D"),
    ({"window_weeks_reported": 250, "window_completeness": 0.96, "window_longest_gap": 2,
      "median_tests_per_week": 80, "weeks_since_last_report": 0}, "A"),
    ({"window_weeks_reported": 200, "window_completeness": 0.77, "window_longest_gap": 20,
      "median_tests_per_week": 80, "weeks_since_last_report": 0}, "B"),
    ({"window_weeks_reported": 50, "window_completeness": 0.2, "window_longest_gap": 120,
      "median_tests_per_week": 5, "weeks_since_last_report": 40}, "C"),
])
def test_assign_tier(row, tier):
    assert assign_tier(row) == tier


def test_staleness_is_never_negative():
    weekly, _ = clean(make_raw(weeks=40, drop_last=2))
    assert (analyse(weekly, window_weeks=30).profiles["weeks_since_last_report"] >= 0).all()


def test_validation_excludes_inconsistent_iso_weeks_and_future_weeks():
    weekly, _ = clean(make_raw(weeks=4, countries=("ARG",), drop_last=0))
    weekly.loc[0, "iso_week"] = 30                     # calendar mismatch
    # Weeks start 1, 8, 15, 22 Jan; on 14 Jan the last two are in the future.
    valid, report = validate_weekly(weekly, today=date(2024, 1, 14))
    assert report["hard"]["week_start_iso_mismatch"]["rows"] == 1
    assert report["hard"]["week_in_future"]["rows"] == 2
    assert report["rows_excluded"] == 3 and len(valid) == 1
