"""Moving Epidemic Method (Vega et al., Influenza Other Respir Viruses 2013; 2015).

A Python port of `memmodel()` from the R package `mem` (v2.19, J. E. Lozano) with its
default settings, validated against it in `pipeline/tests/test_mem.py` (reference values
produced by R; see `scripts/validate_mem.R`):

- **Timing** (`memtiming`, method 2): for each season, the maximum accumulated rates
  percentage (MAP) curve — for every duration *s*, the largest share of the season total
  covered by *s* consecutive weeks — is smoothed with a local-linear normal-kernel
  regression (bandwidth 1). The epidemic lasts *s* weeks where *s + 1* is the first
  duration whose smoothed slope falls below 2.8 percentage points.
- **Epidemic threshold**: from the `n_max` highest pre-epidemic values of each season
  (`n_max` = round(30 / seasons)), the upper limit of a one-sided 95% point interval of
  the arithmetic mean: mean + z(0.95)·sd. The post-epidemic threshold is the same over
  post-epidemic values.
- **Intensity thresholds**: from the `n_max` highest epidemic-period values of each
  season, upper limits of one-sided 40/90/97.5% point intervals of the geometric mean
  (log scale; log(x + 1) when any value is 0) → medium / high / very high.

One deliberate difference: R fills missing weeks inside a season with a kernel smoother
whose bandwidth is chosen by cross-validation (`sm::h.select`); here they are filled by
linear interpolation. Seasons used for thresholds must be ≥ 75% complete, so the effect
is small. Values are in whatever unit is passed in (positivity in percent here).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

#: memmodel defaults.
SLOPE_CRITERION = 2.8
MAX_SEASONS = 10
THRESHOLD_LEVEL = 0.95
INTENSITY_LEVELS = (0.40, 0.90, 0.975)


@dataclass(frozen=True)
class Timing:
    start: int | None   # 0-based index of the first epidemic week (None: no epidemic)
    end: int | None     # inclusive
    duration: int
    percent: float      # share of the season total inside the epidemic period


@dataclass(frozen=True)
class MemResult:
    epidemic_threshold: float
    post_threshold: float | None
    medium: float
    high: float
    very_high: float
    n_seasons: int
    n_max: int
    timings: list[Timing]
    mean_duration: float


def r_round(x: float) -> int:
    """R's round(): half to even (same as Python's round)."""
    return int(round(x))


def fill_missing(x: np.ndarray) -> np.ndarray:
    """Interpolate NaNs strictly inside the observed span; leading/trailing NaN stay."""
    x = np.asarray(x, dtype=float).copy()
    ok = ~np.isnan(x)
    if ok.sum() < 2:
        return x
    idx = np.arange(len(x))
    first, last = idx[ok][0], idx[ok][-1]
    inside = (~ok) & (idx > first) & (idx < last)
    x[inside] = np.interp(idx[inside], idx[ok], x[ok])
    return x


def local_linear(x: np.ndarray, y: np.ndarray, h: float, at: np.ndarray) -> np.ndarray:
    """`sm::sm.regression` default: local-linear fit with a normal kernel of sd `h`.
    Negative estimates are set to 0 (as in mem's `suavizado`)."""
    out = np.empty(len(at))
    for k, x0 in enumerate(at):
        w = norm.pdf((x - x0) / h)
        d = x - x0
        s0, s1, s2 = w.sum(), (w * d).sum(), (w * d * d).sum()
        t0, t1 = (w * y).sum(), (w * d * y).sum()
        den = s0 * s2 - s1 * s1
        out[k] = (s2 * t0 - s1 * t1) / den if den > 0 else t0 / s0
    return np.maximum(out, 0)


def map_curve(x: np.ndarray) -> np.ndarray:
    """MAP curve rows [duration, percent, max_sum, start, end] (1-based start/end, as R),
    with a leading zero row. NaNs count as 0 in sums (R `na.rm = TRUE`)."""
    v = np.nan_to_num(np.asarray(x, dtype=float))
    n = len(v)
    total = v.sum()
    cs = np.concatenate([[0.0], np.cumsum(v)])
    rows = [np.zeros(5)]
    for s in range(1, n + 1):
        sums = cs[s:] - cs[:-s]          # sums[i] = v[i : i + s]
        m = sums.max()
        i = int(np.flatnonzero(sums == m)[0])
        rows.append(np.array([s, 0 if total == 0 else 100 * m / total, m, i + 1, i + s]))
    return np.vstack(rows)


def timing(x: np.ndarray, criterion: float = SLOPE_CRITERION) -> Timing:
    """`memtiming` with method 2 (fixed slope criterion)."""
    curve = map_curve(x)
    dur, pct = curve[:, 0], curve[:, 1]
    smoothed = local_linear(dur, pct, 1.0, dur)
    slope = np.diff(smoothed)
    d_x = dur[1:]
    below = slope < criterion
    optimum = int(max(d_x[below].min() - 1, 1)) if below.any() else int(d_x.max())
    row = curve[curve[:, 0] == optimum][0]
    return Timing(start=int(row[3]) - 1, end=int(row[4]) - 1, duration=optimum,
                  percent=float(row[1]))


def top_n(values: np.ndarray, n: int) -> np.ndarray:
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    return np.sort(v)[::-1][:n]


def upper_point(values: np.ndarray, level: float) -> float:
    """iconfianza.x, one tail: mean + z·sd (sd with n − 1)."""
    v = values[~np.isnan(values)]
    z = norm.ppf(1 - (1 - level))
    return float(v.mean() + z * v.std(ddof=1)) if len(v) > 1 else float("nan")


def upper_point_log(values: np.ndarray, level: float) -> float:
    """iconfianza.logx, one tail: geometric version; log(x + 1) when any value is 0."""
    v = values[~np.isnan(values)]
    if len(v) < 2:
        return float("nan")
    if np.all(v != 0):
        return float(np.exp(upper_point(np.log(v), level)))
    return float(np.exp(upper_point(np.log(v + 1), level)) - 1)


def memmodel(seasons: list[np.ndarray]) -> MemResult | None:
    """Thresholds from past seasons (oldest first). Each season is its weekly values in
    season order. Seasons with no non-zero value are dropped; at most the latest 10 are
    used. Returns None with fewer than 2 seasons (R refuses too)."""
    data = [fill_missing(s) for s in seasons if np.nansum(s) > 0][-MAX_SEASONS:]
    if len(data) < 2:
        return None
    n_max = max(1, r_round(30 / len(data)))

    pre, post, epi, timings = [], [], [], []
    for x in data:
        t = timing(x)
        timings.append(t)
        pre.append(top_n(x[: t.start], n_max))
        epi.append(top_n(x[t.start: t.end + 1], n_max))
        post.append(top_n(x[t.end + 1:], n_max))
    pre_v, post_v, epi_v = (np.concatenate(a) for a in (pre, post, epi))

    medium, high, very_high = (upper_point_log(epi_v, lvl) for lvl in INTENSITY_LEVELS)
    post_t = upper_point(post_v, THRESHOLD_LEVEL)
    return MemResult(
        epidemic_threshold=upper_point(pre_v, THRESHOLD_LEVEL),
        post_threshold=None if np.isnan(post_t) else post_t,
        medium=medium, high=high, very_high=very_high,
        n_seasons=len(data), n_max=n_max, timings=timings,
        mean_duration=float(np.mean([t.duration for t in timings])),
    )
