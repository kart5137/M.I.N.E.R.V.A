"""Row-level validation of cleaned weekly and monthly surveillance data.

Rows failing a *hard* check are excluded from loading; every check's count and a few
examples go into the ingestion run's quality report. *Soft* checks are only counted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

import pandas as pd

MAX_EXAMPLES = 5
FLU_COUNTS = ("specimens_tested", "positives")


def _examples(df: pd.DataFrame, period: str) -> list[dict]:
    cols = [c for c in ("country_code", "iso_year", "iso_week", period) if c in df]
    return df[cols].head(MAX_EXAMPLES).astype(str).to_dict("records")


def _apply(df: pd.DataFrame, hard: Mapping[str, pd.Series], soft: Mapping[str, pd.Series],
           key: Sequence[str], period: str) -> tuple[pd.DataFrame, dict]:
    failed = pd.Series(False, index=df.index)
    report: dict = {"hard": {}, "soft": {}}
    for name, mask in hard.items():
        mask = mask.fillna(False).astype(bool)
        failed |= mask
        report["hard"][name] = {"rows": int(mask.sum()), "examples": _examples(df[mask], period)}
    for name, mask in soft.items():
        report["soft"][name] = int(mask.fillna(False).astype(bool).sum())

    dupes = df.duplicated(list(key), keep=False)
    if dupes.any():
        raise ValueError(f"{int(dupes.sum())} duplicate {'/'.join(key)} keys after cleaning")

    report["rows_in"] = len(df)
    report["rows_excluded"] = int(failed.sum())
    return df[~failed].copy(), report


def _common_hard(df: pd.DataFrame, period: str, today: pd.Timestamp,
                 count_cols: Sequence[str]) -> dict[str, pd.Series]:
    return {
        "bad_country_code": ~df["country_code"].astype(str).str.fullmatch(r"[A-Z0-9]{3}"),
        f"{period}_in_future": df[period] > today,
        "negative_counts": (df[list(count_cols)] < 0).any(axis=1),
    }


def validate_weekly(weekly: pd.DataFrame, today: date | None = None, *,
                    count_cols: Sequence[str] = FLU_COUNTS,
                    soft: Mapping[str, pd.Series] | None = None) -> tuple[pd.DataFrame, dict]:
    """Weekly rows keyed by (country_code, week_start). `soft` defaults to the FluNet
    checks; other sources pass their own."""
    today = pd.Timestamp(today or date.today())
    iso = weekly["week_start"].dt.isocalendar()
    common = _common_hard(weekly, "week_start", today, count_cols)
    hard = {
        "bad_country_code": common["bad_country_code"],
        "iso_week_out_of_range": ~weekly["iso_week"].between(1, 53),
        "week_start_not_monday": weekly["week_start"].dt.dayofweek != 0,
        "week_start_iso_mismatch": (iso["year"].astype(int) != weekly["iso_year"])
        | (iso["week"].astype(int) != weekly["iso_week"]),
        "week_in_future": common["week_start_in_future"],
        "negative_counts": common["negative_counts"],
    }
    if soft is None:
        soft = {
            "positives_exceed_tests": weekly["positives"] > weekly["specimens_tested"],
            "no_specimens_tested": ~weekly["reported"],
        }
    return _apply(weekly, hard, soft, ("country_code", "week_start"), "week_start")


def validate_monthly(monthly: pd.DataFrame, today: date | None = None, *,
                     count_cols: Sequence[str] = ("cases",),
                     soft: Mapping[str, pd.Series] | None = None) -> tuple[pd.DataFrame, dict]:
    """Monthly rows keyed by (country_code, month_start). A month is "in the future"
    when it has not started yet."""
    today = pd.Timestamp(today or date.today())
    common = _common_hard(monthly, "month_start", today, count_cols)
    hard = {
        "bad_country_code": common["bad_country_code"],
        "month_start_not_first_day": monthly["month_start"].dt.day != 1,
        "month_in_future": common["month_start_in_future"],
        "negative_counts": common["negative_counts"],
    }
    return _apply(monthly, hard, soft or {}, ("country_code", "month_start"), "month_start")
