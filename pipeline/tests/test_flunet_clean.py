from __future__ import annotations

import pandas as pd

from conftest import make_raw
from ei_pipeline.sources.flunet import clean


def test_one_row_per_country_week_and_positivity():
    weekly, rep = clean(make_raw(weeks=10, countries=("ARG",), drop_last=0))
    assert len(weekly) == 10 and rep.country_weeks == 10
    row = weekly.iloc[3]
    assert row["positivity"] == row["positives"] / row["specimens_tested"]


def test_exact_duplicates_dropped():
    raw = make_raw(weeks=5, countries=("ARG",), drop_last=0)
    weekly, rep = clean(pd.concat([raw, raw.iloc[:2]]))
    assert rep.exact_duplicates_dropped == 2 and len(weekly) == 5


def test_notdefined_dropped_when_sentinel_present_for_same_week():
    raw = make_raw(weeks=3, countries=("AUT",), drop_last=0)
    dup = raw.iloc[[0]].assign(ORIGIN_SOURCE="NOTDEFINED")  # repeats the sentinel figures
    weekly, rep = clean(pd.concat([raw, dup]))
    assert rep.notdefined_rows_dropped == 1
    assert weekly.iloc[0]["specimens_tested"] == raw.iloc[0]["SPEC_PROCESSED_NB"]


def test_sentinel_and_nonsentinel_are_summed():
    raw = make_raw(weeks=1, countries=("AUT",), drop_last=0)
    non = raw.assign(ORIGIN_SOURCE="NONSENTINEL")
    weekly, _ = clean(pd.concat([raw, non]))
    assert weekly.iloc[0]["specimens_tested"] == 2 * raw.iloc[0]["SPEC_PROCESSED_NB"]


def test_positives_fall_back_to_a_plus_b():
    raw = make_raw(weeks=2, countries=("ARG",), drop_last=0).assign(INF_ALL=None)
    weekly, rep = clean(raw)
    assert rep.positives_from_a_plus_b == 2
    assert (weekly["positives"] == raw["INF_A"].values + raw["INF_B"].values).all()


def test_uk_nations_summed_into_gbr():
    raw = make_raw(weeks=2, countries=("X09", "X10"), drop_last=0)
    weekly, rep = clean(raw)
    assert set(weekly["country_code"]) == {"GBR"}
    assert rep.uk_nation_rows_aggregated == 4
    assert weekly.iloc[0]["specimens_tested"] == 2 * raw.iloc[0]["SPEC_PROCESSED_NB"]


def test_positives_exceeding_tests_get_no_positivity():
    raw = make_raw(weeks=1, countries=("ARG",), drop_last=0).assign(
        SPEC_PROCESSED_NB=1, INF_ALL=5, INF_A=3, INF_B=2)
    weekly, rep = clean(raw)
    assert rep.positives_exceed_tests == 1 and pd.isna(weekly.iloc[0]["positivity"])


def test_zero_tests_is_not_a_reported_week():
    raw = make_raw(weeks=1, countries=("ARG",), drop_last=0).assign(
        SPEC_PROCESSED_NB=0, INF_ALL=0, INF_A=0, INF_B=0, INF_NEGATIVE=0)
    weekly, _ = clean(raw)
    assert not weekly.iloc[0]["reported"] and pd.isna(weekly.iloc[0]["positivity"])
