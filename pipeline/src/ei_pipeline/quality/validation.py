"""Row-level validation of cleaned weekly surveillance data.

Rows failing a *hard* check are excluded from loading; every check's count and a few
examples go into the ingestion run's quality report.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

MAX_EXAMPLES = 5


def _examples(df: pd.DataFrame) -> list[dict]:
    cols = [c for c in ("country_code", "iso_year", "iso_week", "week_start") if c in df]
    return df[cols].head(MAX_EXAMPLES).astype(str).to_dict("records")


def validate_weekly(weekly: pd.DataFrame, today: date | None = None) -> tuple[pd.DataFrame, dict]:
    today = pd.Timestamp(today or date.today())
    iso = weekly["week_start"].dt.isocalendar()

    hard = {
        "bad_country_code": ~weekly["country_code"].astype(str).str.fullmatch(r"[A-Z0-9]{3}"),
        "iso_week_out_of_range": ~weekly["iso_week"].between(1, 53),
        "week_start_not_monday": weekly["week_start"].dt.dayofweek != 0,
        "week_start_iso_mismatch": (iso["year"].astype(int) != weekly["iso_year"])
        | (iso["week"].astype(int) != weekly["iso_week"]),
        "week_in_future": weekly["week_start"] > today,
        "negative_counts": (weekly[["specimens_tested", "positives"]] < 0).any(axis=1),
    }
    soft = {
        "positives_exceed_tests": weekly["positives"] > weekly["specimens_tested"],
        "no_specimens_tested": ~weekly["reported"],
    }

    failed = pd.Series(False, index=weekly.index)
    report: dict = {"hard": {}, "soft": {}}
    for name, mask in hard.items():
        mask = mask.fillna(False)
        failed |= mask
        report["hard"][name] = {"rows": int(mask.sum()), "examples": _examples(weekly[mask])}
    for name, mask in soft.items():
        report["soft"][name] = int(mask.fillna(False).sum())

    dupes = weekly.duplicated(["country_code", "week_start"], keep=False)
    if dupes.any():
        raise ValueError(f"{int(dupes.sum())} duplicate country-week keys after cleaning")

    report["rows_in"] = len(weekly)
    report["rows_excluded"] = int(failed.sum())
    return weekly[~failed].copy(), report
