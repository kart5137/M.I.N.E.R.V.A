"""Hotspots: local spatial statistics on 4-week pooled positivity (DESIGN.md §6.5).

For every 4-week window ending on a week from HOTSPOTS_FROM to the latest week:

- Input: pooled positivity Σ positives / Σ specimens per country over the window (rows
  with tests > 0, like the map), for countries with geometry and ≥ MIN_TESTS specimens.
  Other countries do not participate and are shown as "no data", never "cold".
- Weights: queen contiguity among participants, k = 4 nearest for countries with none;
  binary, row-standardised. Gi* includes the country itself.
- Getis-Ord Gi* (hot/cold spots) and Local Moran's I (HH/LL clusters, HL/LH outliers).
- Inference: conditional permutation (the country's value fixed, its neighbours drawn
  from the other participants), 999 permutations, folded pseudo p-value as in PySAL
  `esda`; z = (observed − mean of permutations) / their sd. Benjamini–Hochberg FDR per
  window and statistic; significant at p_fdr < 0.05.

Dengue (D4): the input is the mean weekly incidence per 100,000 over the window's
reported weeks (≥ 2 of 4; gaps are not zeros), and the statistics run on
log(1 + incidence) so that a few very high countries do not dominate. Case definitions
differ between countries, so a dengue hot spot is a cluster of high *reported*
incidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ei_pipeline.detection import config as cfg
from ei_pipeline.detection.weights import Geography, Neighbours, neighbours


@dataclass
class HotspotRow:
    iso3: str
    window_end: date
    window_weeks: int
    statistic: str
    value: float
    stat_value: float
    z_score: float
    p_value: float
    p_fdr: float
    classification: str
    n_neighbours: int
    neighbour_source: str


def bh_fdr(p: np.ndarray) -> np.ndarray:
    """Benjamini–Hochberg adjusted p-values."""
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(adj, 1.0)
    return out


def _perm_ids(n: int, kmax: int, perms: int, rng: np.random.Generator) -> np.ndarray:
    """perms × kmax indices into 'the other n − 1 values', without replacement per row."""
    return np.argsort(rng.random((perms, n - 1)), axis=1)[:, :kmax]


def _folded_p(obs: float, sims: np.ndarray) -> float:
    """One-sided pseudo p-value in the direction of the observation. Ties count against
    significance on both sides: with many countries at 0% positivity, esda's
    `(sims >= obs)` folding would call a tie at the minimum 'extreme' (p = 0.001)."""
    tol = 1e-12 * max(1.0, abs(obs))
    at_least = int(np.sum(sims >= obs - tol))
    at_most = int(np.sum(sims <= obs + tol))
    return (min(at_least, at_most) + 1) / (len(sims) + 1)


def local_statistics(x: np.ndarray, nb: Neighbours, perms: int, rng: np.random.Generator
                     ) -> dict[str, dict[str, np.ndarray]]:
    """Gi* and Local Moran's I with conditional-permutation inference."""
    n = len(x)
    kmax = max(len(ix) for ix in nb.lists)
    ids = _perm_ids(n, kmax, perms, rng)
    z = x - x.mean()
    m2 = (z ** 2).sum() / n

    out = {s: {k: np.empty(n) for k in ("stat", "z", "p", "lag")}
           for s in ("gi_star", "local_moran")}
    for i, idx in enumerate(nb.lists):
        k = len(idx)
        sample = ids[:, :k]
        sample = sample + (sample >= i)          # skip i itself
        nb_sum_sim = x[sample].sum(axis=1)
        nb_sum = x[idx].sum()
        # Gi*: row-standardised weights over the neighbours and the country itself.
        gi = (x[i] + nb_sum) / (k + 1)
        gi_sim = (x[i] + nb_sum_sim) / (k + 1)
        # Local Moran: row-standardised spatial lag of the deviations.
        lag = nb_sum / k - x.mean()
        lag_sim = nb_sum_sim / k - x.mean()
        mi, mi_sim = z[i] * lag / m2, z[i] * lag_sim / m2
        for name, obs, sims in (("gi_star", gi, gi_sim), ("local_moran", mi, mi_sim)):
            sd = sims.std(ddof=1)
            out[name]["stat"][i] = obs
            out[name]["z"][i] = (obs - sims.mean()) / sd if sd > 0 else 0.0
            out[name]["p"][i] = _folded_p(obs, sims)
        out["local_moran"]["lag"][i] = lag
    return out


def classify(stat: str, zval: float, p_fdr: float, dev: float, lag: float) -> str:
    if p_fdr >= cfg.FDR_ALPHA:
        return "ns"
    if stat == "gi_star":
        return "hot" if zval > 0 else "cold"
    return {(True, True): "HH", (False, False): "LL",
            (True, False): "HL", (False, True): "LH"}[(dev > 0, lag > 0)]


def window_values(weekly: pd.DataFrame, end: date, weeks: int,
                  spec: cfg.DetectionSpec = cfg.INFLUENZA) -> pd.Series:
    """Pooled positivity per country for the window, ≥ MIN_TESTS specimens; dengue: mean
    weekly incidence over the reported weeks (≥ DENGUE_HOTSPOT_MIN_WEEKS)."""
    start = pd.Timestamp(end) - pd.Timedelta(weeks=weeks - 1)
    if spec.metric == "incidence":
        w = weekly[(weekly["week_start"] >= start)
                   & (weekly["week_start"] <= pd.Timestamp(end)) & weekly["p"].notna()]
        g = w.groupby("iso3")["p"].agg(["mean", "count"])
        return g.loc[g["count"] >= cfg.DENGUE_HOTSPOT_MIN_WEEKS, "mean"].sort_index()
    w = weekly[(weekly["week_start"] >= start) & (weekly["week_start"] <= pd.Timestamp(end))
               & (weekly["tests"] > 0) & (weekly["positives"] <= weekly["tests"])]
    g = w.groupby("iso3")[["positives", "tests"]].sum()
    g = g[g["tests"] >= cfg.MIN_TESTS]
    return (g["positives"] / g["tests"]).sort_index()


def hotspots_for_window(weekly: pd.DataFrame, geo: Geography, end: date,
                        weeks: int = cfg.HOTSPOT_WINDOW_WEEKS,
                        spec: cfg.DetectionSpec = cfg.INFLUENZA) -> list[HotspotRow]:
    values = window_values(weekly, end, weeks, spec)
    nb = neighbours(geo, list(values.index), cfg.KNN_K)
    if len(nb.codes) < 10:
        return []
    raw = values.reindex(nb.codes).to_numpy(dtype=float)
    x = np.log1p(raw) if spec.metric == "incidence" else raw
    rng = np.random.default_rng(cfg.HOTSPOT_SEED + end.toordinal())
    res = local_statistics(x, nb, cfg.PERMUTATIONS, rng)
    dev = x - x.mean()
    rows = []
    for stat, r in res.items():
        p_fdr = bh_fdr(r["p"])
        for i, iso3 in enumerate(nb.codes):
            rows.append(HotspotRow(
                iso3=iso3, window_end=end, window_weeks=weeks, statistic=stat,
                value=float(raw[i]), stat_value=float(r["stat"][i]), z_score=float(r["z"][i]),
                p_value=float(r["p"][i]), p_fdr=float(p_fdr[i]),
                classification=classify(stat, r["z"][i], p_fdr[i], dev[i],
                                        res["local_moran"]["lag"][i]),
                n_neighbours=len(nb.lists[i]), neighbour_source=nb.source[i],
            ))
    return rows


def compute_hotspots(weekly: pd.DataFrame, geo: Geography, latest_week: date,
                     spec: cfg.DetectionSpec = cfg.INFLUENZA) -> list[HotspotRow]:
    out, end = [], cfg.HOTSPOTS_FROM
    while end <= latest_week:
        out += hotspots_for_window(weekly, geo, end, spec=spec)
        end += timedelta(weeks=1)
    return out
