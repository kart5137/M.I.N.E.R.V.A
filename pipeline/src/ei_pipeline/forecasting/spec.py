"""What is forecast for each disease, and the few rules that differ between targets.

The backtest, conformal intervals, evaluation, selection and registry are shared; a
`TargetSpec` supplies the target's scale (the transform models are trained on), its
features, the models compared, and the volume groups used for Mondrian conformal.

- **Influenza test positivity** (M5): logit of smoothed positivity; intervals calibrated
  per testing-volume group (specimens per week).
- **Dengue incidence** (D4): log(weekly cases per 100,000 + one case per 100,000
  population); tree models learn the change from this week; intervals calibrated per
  case-count group (cases per week). Tree models are fitted twice, with and without the
  ERA5 weather features, and a weather model becomes active only if it wins the backtest.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from ei_pipeline.forecasting import config as cfg


def logit(p):
    return np.log(p / (1 - p))


def expit(x):
    return 1 / (1 + np.exp(-x))


#: Influenza point forecasts are clipped to this positivity range before the logit.
P_CLIP = (0.001, 0.999)


@dataclass(frozen=True)
class TargetSpec:
    disease: str
    target: str
    #: Features of the plain tree models.
    features: tuple[str, ...]
    #: ML model name → its feature list (defaults to `features`).
    model_features: dict[str, tuple[str, ...]] = field(default_factory=dict)
    ml_models: tuple[str, ...] = cfg.ML_MODELS
    #: Mondrian conformal groups: edges on the 4-week mean volume at the origin.
    volume_edges: tuple[float, ...] = cfg.CONFORMAL_GROUP_EDGES
    #: What the volume is (for reports).
    volume_label: str = "Specimens/week"
    #: Floor of the volatility scale on the model scale.
    scale_floor: float = cfg.SCALE_FLOOR
    #: Training excludes target weeks in the COVID-19 window.
    exclude_covid: bool = True
    #: Natural scale → model scale, and back: f(values, offset). The offset is per row
    #: (dengue: one case per 100,000 population); influenza ignores it.
    to_y: Callable = field(default=lambda p, off=None: logit(np.clip(
        np.asarray(p, dtype=float), *P_CLIP)))
    from_y: Callable = field(default=lambda y, off=None: expit(y))
    #: Lower and upper bound of the natural scale (None = unbounded).
    bounds: tuple[float | None, float | None] = (0.0, 1.0)
    card_name: str = "influenza-positivity.md"
    #: Tree models learn the change from this week, y(t + h) − y(t), instead of the level.
    #: Trees cannot predict beyond the range seen in training, and dengue reaches record
    #: levels (e.g. 2024 in the Americas); a change (a growth factor on the log scale)
    #: transfers between countries and years.
    delta_target: bool = False

    def features_for(self, model: str) -> tuple[str, ...]:
        return self.model_features.get(model, self.features)

    @property
    def all_features(self) -> tuple[str, ...]:
        seen = dict.fromkeys(self.features)
        for f in self.model_features.values():
            seen.update(dict.fromkeys(f))
        return tuple(seen)

    def interval(self, point_y, half, off=None) -> tuple[np.ndarray, np.ndarray]:
        """Bounds on the natural scale. For positivity, a bound that reaches the clip
        range becomes 0 or 1 so that 0% (or 100%) weeks can be covered; incidence bounds
        are floored at 0."""
        point_y, half = np.asarray(point_y, dtype=float), np.asarray(half, dtype=float)
        lo = self.from_y(point_y - half, off)
        hi = self.from_y(point_y + half, off)
        if self.target == "positivity":
            return (np.where(lo <= P_CLIP[0] * 1.0001, 0.0, lo),
                    np.where(hi >= P_CLIP[1] * 0.9999, 1.0, hi))
        return np.maximum(lo, 0.0), hi


def _offset(off) -> np.ndarray | float:
    return 1.0 if off is None else np.asarray(off, dtype=float)


def log_incidence(v, off=None):
    """log(incidence + offset); the offset is one reported case per 100,000 population
    (100,000 ÷ population), so this is log(cases + 1) shifted by log population: changes
    are relative changes for every country, and a single case is not an outbreak."""
    return np.log(np.clip(np.asarray(v, dtype=float), 0.0, None) + _offset(off))


def from_log_incidence(y, off=None):
    return np.maximum(np.exp(np.asarray(y, dtype=float)) - _offset(off), 0.0)


def influenza() -> TargetSpec:
    from ei_pipeline.forecasting.features import FEATURES
    return TargetSpec(disease="influenza", target=cfg.TARGET, features=tuple(FEATURES))


def dengue() -> TargetSpec:
    from ei_pipeline.forecasting import dengue_config as dcfg
    from ei_pipeline.forecasting.features import DENGUE_FEATURES, WEATHER_FEATURES
    base = tuple(DENGUE_FEATURES)
    with_weather = base + tuple(WEATHER_FEATURES)
    return TargetSpec(
        disease="dengue", target=dcfg.TARGET, features=base,
        model_features={f"{m}_weather": with_weather for m in cfg.ML_MODELS},
        ml_models=(*cfg.ML_MODELS, *(f"{m}_weather" for m in cfg.ML_MODELS)),
        volume_edges=dcfg.CONFORMAL_GROUP_EDGES, volume_label="Cases/week",
        scale_floor=dcfg.SCALE_FLOOR, exclude_covid=False,
        to_y=log_incidence, from_y=from_log_incidence, bounds=(0.0, None),
        card_name="dengue-incidence.md", delta_target=True,
    )


def get(disease: str) -> TargetSpec:
    try:
        return {"influenza": influenza, "dengue": dengue}[disease]()
    except KeyError:
        raise ValueError(f"No forecasting target for disease '{disease}'") from None


DISEASES = ("influenza", "dengue")
