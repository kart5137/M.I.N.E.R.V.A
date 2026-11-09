"""Detection (M6): MEM against the R reference, thresholds scope and quality gate, risk
rule, anomalies, spatial statistics, and one end-to-end run."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from ei_pipeline.detection import config as cfg
from ei_pipeline.detection.anomalies import seasonal_ewma_anomalies, severity_of
from ei_pipeline.detection.hotspots import _folded_p, bh_fdr, local_statistics
from ei_pipeline.detection.mem import fill_missing, memmodel
from ei_pipeline.detection.risk import risk_level
from ei_pipeline.detection.thresholds import compute_thresholds, quality_issue
from ei_pipeline.detection.weights import Geography, neighbours

DATA = Path(__file__).parent / "data"

# Produced by scripts/validate_mem.R with R mem 2.19 (memmodel defaults).
R_REFERENCE = {
    "mem_flucyl": {
        "levels": (53.3364493501, 60.4864309717, 249.9234334643, 441.8986300204,
                   568.4895963501),
        "start": [14, 11, 3, 12, 19, 15, 12, 11],
        "end": [23, 26, 12, 19, 28, 22, 22, 20],
    },
    # Synthetic: 41 zero weeks (log(x + 1) path) and one 53-week season.
    "mem_synthetic": {
        "levels": (13.4035184570, 9.8090672003, 27.3644218596, 32.3282496567,
                   34.8001072213),
        "start": [10, 12, 18, 13, 15, 9],
        "end": [19, 24, 28, 22, 26, 20],
    },
}


# ---------- MEM ----------

@pytest.mark.parametrize("name", sorted(R_REFERENCE))
def test_mem_matches_r_package(name):
    d = pd.read_csv(DATA / f"{name}.csv", index_col=0)
    r = memmodel([d[c].to_numpy(float) for c in d.columns])
    ref = R_REFERENCE[name]
    got = (r.epidemic_threshold, r.post_threshold, r.medium, r.high, r.very_high)
    assert got == pytest.approx(ref["levels"], abs=1e-8)
    assert [t.start + 1 for t in r.timings] == ref["start"]
    assert [t.end + 1 for t in r.timings] == ref["end"]


def test_mem_needs_two_nonzero_seasons_and_fills_inner_gaps_only():
    assert memmodel([np.ones(52)]) is None
    assert memmodel([np.ones(52), np.zeros(52)]) is None
    x = fill_missing(np.array([np.nan, 1.0, np.nan, 3.0, np.nan]))
    assert np.isnan(x[0]) and x[2] == 2.0 and np.isnan(x[4])


def test_quality_gate():
    assert quality_issue(10, 20, 30, 40) is None
    assert "not ordered" in quality_issue(30, 20, 40, 50)
    assert "100%" in quality_issue(10, 20, 30, 120)
    assert "not above 0" in quality_issue(0, 20, 30, 40)


def _seasonal_weekly(iso3: str, start: date, end: date, peak_week: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range(start, end, freq="7D")
    iso_w = weeks.isocalendar().week.to_numpy().astype(float)
    dist = np.minimum(np.abs(iso_w - peak_week), 52 - np.abs(iso_w - peak_week))
    p = 0.02 + 0.30 * np.exp(-0.5 * (dist / 3) ** 2) + rng.normal(0, 0.005, len(weeks))
    p = np.clip(p, 0, 1)
    tests = np.full(len(weeks), 500.0)
    df = pd.DataFrame({"iso3": iso3, "week_start": weeks, "tests": tests,
                       "positives": np.round(p * tests), "is_provisional": False})
    df["p"] = df["positives"] / df["tests"]
    df["covid"] = df["week_start"].between(pd.Timestamp(cfg.COVID_START),
                                           pd.Timestamp(cfg.COVID_END))
    return df


def test_thresholds_skip_covid_and_year_round_and_need_three_seasons():
    weekly = pd.concat([
        _seasonal_weekly("NHC", date(2012, 10, 1), date(2026, 3, 30), peak_week=4),
        _seasonal_weekly("YRC", date(2012, 10, 1), date(2026, 3, 30), peak_week=20, seed=1),
        _seasonal_weekly("NEW", date(2023, 10, 2), date(2026, 3, 30), peak_week=4, seed=2),
    ])
    countries = pd.DataFrame({"iso3": ["NHC", "YRC", "NEW"], "name": ["a", "b", "c"],
                              "flu_season": ["NH", "YR", "NH"]})
    rows, not_assessed = compute_thresholds(weekly, countries, date(2026, 3, 30),
                                            date(2026, 3, 30))
    nh = [r for r in rows if r.iso3 == "NHC"]
    assert nh and not any(r.iso3 in ("YRC", "NEW") for r in rows)
    assert "year-round" in not_assessed["YRC"] and "needs 3" in not_assessed["NEW"]
    current = nh[-1]
    assert current.season == "2025/26"
    # COVID-overlapping seasons (2019/20 – 2021/22) are never used.
    assert not {"2019/20", "2020/21", "2021/22"} & set(current.seasons_used)
    assert current.quality_note is None
    assert 0 < current.epidemic_threshold < current.medium < current.high < current.very_high < 1


def test_risk_rule():
    assert risk_level(0.05, epidemic=0.10, high=0.30) == "low"
    assert risk_level(0.10, epidemic=0.10, high=0.30) == "moderate"
    assert risk_level(0.30, epidemic=0.10, high=0.30) == "high"


# ---------- anomalies ----------

def test_anomaly_flags_unseasonal_surge_but_not_normal_season():
    df = _seasonal_weekly("AAA", date(2013, 1, 7), date(2025, 12, 29), peak_week=4)
    surge = df["week_start"].between("2025-07-07", "2025-08-04")  # off-season, 5 weeks
    df.loc[surge, "positives"] = 200
    df["p"] = df["positives"] / df["tests"]
    flagged, _ = seasonal_ewma_anomalies("AAA", df)
    weeks = {a.week_start for a in flagged}
    surge_weeks = {date(2025, 7, 7) + pd.Timedelta(weeks=i).to_pytimedelta() for i in range(5)}
    assert surge_weeks <= weeks
    # Outside the surge and its EWMA tail, the normal seasons are (almost) never flagged.
    others = {w for w in weeks if not date(2025, 7, 7) <= w <= date(2025, 8, 18)}
    assert len(others) <= 2
    assert all(a.observed > a.upper_band and a.ewma > a.ewma_limit for a in flagged)
    assert severity_of(2.0) == "moderate" and severity_of(3.0) == "high"
    assert severity_of(7.0) == "severe"


# ---------- spatial statistics ----------

def test_bh_fdr_matches_hand_computation():
    p = np.array([0.01, 0.04, 0.03, 0.20])
    # sorted 0.01, 0.03, 0.04, 0.20 → ×4/rank = 0.04, 0.06, 0.0533, 0.20 → monotone
    assert bh_fdr(p) == pytest.approx([0.04, 0.0533333, 0.0533333, 0.20])


def test_folded_p_counts_ties_against_significance():
    sims = np.zeros(999)
    assert _folded_p(0.0, sims) == 1.0          # all ties: nothing extreme
    assert _folded_p(1.0, sims) == pytest.approx(1 / 1000)


def test_gi_star_finds_high_cluster_on_a_line():
    # 30 countries on a line, each touching its neighbours; a high block in the middle.
    codes = [f"C{i:02d}" for i in range(30)]
    contig = {c: frozenset(codes[j] for j in (i - 1, i + 1) if 0 <= j < 30)
              for i, c in enumerate(codes)}
    geo = Geography(contiguity=contig, centroids={c: (i, 0.0) for i, c in enumerate(codes)})
    nb = neighbours(geo, codes, k=4)
    x = np.full(30, 0.05)
    x[13:17] = 0.40
    res = local_statistics(x, nb, 999, np.random.default_rng(0))
    gi = res["gi_star"]
    assert gi["z"][14] > 2 and gi["p"][14] < 0.05
    assert abs(gi["z"][0]) < 2
    assert res["local_moran"]["stat"][14] > 0  # high among high: positive I


def test_neighbours_fall_back_to_nearest_for_islands():
    geo = Geography(contiguity={"A": frozenset({"B"}), "B": frozenset({"A"}),
                                "I": frozenset()},
                    centroids={"A": (0, 0), "B": (1, 0), "I": (50, 0), "J": (51, 0)})
    nb = neighbours(geo, ["A", "B", "I", "J"], k=2)
    assert nb.source == ["queen", "queen", "knn", "knn"]
    assert [nb.codes[j] for j in nb.lists[2]] == ["J", "B"]


# ---------- end to end ----------

def _seed(engine):
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO data_sources (id, key, name) VALUES (1, 'flunet', 'FluNet');
            INSERT INTO diseases (id, key, name, native_granularity, primary_metric,
                                  metric_label)
              VALUES (1, 'influenza', 'Influenza', 'weekly', 'positivity', 'Positivity');
            INSERT INTO ingestion_runs (id, source_id, status) VALUES (1, 1, 'success');
        """))
        squares = []
        for i in range(12):
            x0 = (i % 4) * 10
            y0 = (i // 4) * 10
            squares.append((f"C{i:02d}", x0, y0))
        for code, x0, y0 in squares:
            c.execute(text("""
                INSERT INTO countries (iso3, name, flu_season, geom, centroid) VALUES
                (CAST(:c AS varchar), CAST(:c AS varchar), 'NH',
                 ST_Multi(ST_MakeEnvelope(:x0, :y0, :x0 + 10, :y0 + 10, 4326)),
                 ST_SetSRID(ST_MakePoint(:x0 + 5, :y0 + 5), 4326))
            """), {"c": code, "x0": x0, "y0": y0})
        weekly = pd.concat([_seasonal_weekly(code, date(2013, 1, 7), date(2025, 3, 3),
                                             peak_week=4 + (i % 3), seed=i)
                            for i, (code, _, _) in enumerate(squares)])
        weekly = weekly[~weekly["covid"]]
        recs = [{"i": r.iso3, "w": r.week_start.date(), "y": r.week_start.isocalendar()[0],
                 "k": r.week_start.isocalendar()[1], "t": int(r.tests), "p": int(r.positives)}
                for r in weekly.itertuples()]
        c.execute(text("""
            INSERT INTO surveillance_weekly (disease_id, iso3, week_start, iso_year, iso_week,
              specimens_tested, positives, positivity, is_provisional, source_id,
              ingestion_run_id)
            VALUES (1, :i, :w, :y, :k, :t, :p, CAST(:p AS float) / :t, false, 1, 1)
        """), recs)


def test_end_to_end_detection_run(db, monkeypatch):
    from ei_pipeline.detection import run as run_mod

    monkeypatch.setattr(cfg, "HOTSPOTS_FROM", date(2025, 2, 3))
    _seed(db)
    summary = run_mod.run_detection(db)
    q = lambda sql: db.connect().execute(text(sql)).scalar()  # noqa: E731
    assert q("SELECT count(*) FROM detection_runs WHERE finished_at IS NOT NULL") == 1
    assert summary["thresholds_current_usable"] == 12
    # 4-neighbour grid: queen contiguity only, so no kNN fallback; Gi* + Moran per window.
    assert q("SELECT count(*) FROM hotspot_results WHERE neighbour_source = 'knn'") == 0
    assert q("SELECT count(DISTINCT window_end) FROM hotspot_results") == 5
    assert q("SELECT count(*) FROM hotspot_results") == 5 * 12 * 2
    assert q("SELECT bool_and(p_fdr >= p_value - 1e-12) FROM hotspot_results")
    # No forecasts in this database → no risk rows.
    assert q("SELECT count(*) FROM risk_assessments") == 0
    # A second run replaces the outputs.
    run_mod.run_detection(db)
    assert q("SELECT count(*) FROM hotspot_results") == 5 * 12 * 2
    assert q("SELECT count(DISTINCT run_id) FROM seasonal_thresholds") == 1
    assert q("SELECT count(*) FROM detection_runs") == 2

