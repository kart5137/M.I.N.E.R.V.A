"""Model factory. ML models predict the target on the model scale (logit positivity, or
log(incidence + one case per 100,000)); baselines are read from the frame. `*_weather`
models are the same algorithms fitted on a larger feature set (dengue, D4)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor

from ei_pipeline.forecasting import config as cfg
from ei_pipeline.forecasting.spec import P_CLIP, TargetSpec, influenza

__all__ = ["P_CLIP", "fit", "interval", "make_model", "offset", "predict_p", "row_offset",
           "to_logit", "training_rows"]


def _spec(spec: TargetSpec | None) -> TargetSpec:
    return spec if spec is not None else influenza()


def make_model(name: str, hp: cfg.Hyperparams):
    algorithm = name.removesuffix("_weather")
    if algorithm == "random_forest":
        return RandomForestRegressor(**hp.rf)
    if algorithm == "xgboost":
        return XGBRegressor(**hp.xgb)
    raise ValueError(name)


def training_rows(frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Rows whose target week is known by `cutoff` and usable as a target."""
    return frame[(frame["target_week"] <= cutoff) & frame["trainable"]
                 & (frame["target_week"] >= pd.Timestamp(cfg.TRAIN_START))]


def fit(name: str, frame: pd.DataFrame, cutoff: pd.Timestamp, hp: cfg.Hyperparams,
        spec: TargetSpec | None = None):
    spec = _spec(spec)
    features = list(spec.features_for(name))
    rows = training_rows(frame, cutoff)
    label = rows["actual_y"]
    if spec.delta_target:
        rows = rows[rows["y_lag0"].notna()]
        label = rows["actual_y"] - rows["y_lag0"]
    model = make_model(name, hp)
    model.fit(rows[features].to_numpy(dtype=float), label.to_numpy(dtype=float))
    model.ei_features = features
    model.ei_delta = spec.delta_target
    return model, rows


def offset(model, rows: pd.DataFrame) -> np.ndarray:
    """What the model output is added to: this week's value for change targets."""
    if getattr(model, "ei_delta", False):
        return rows["y_lag0"].to_numpy(dtype=float)
    return np.zeros(len(rows))


def row_offset(rows: pd.DataFrame):
    """Per-row transform offset (dengue), or None."""
    return rows["offset"].to_numpy(dtype=float) if "offset" in rows else None


def predict_p(model, rows: pd.DataFrame, spec: TargetSpec | None = None) -> np.ndarray:
    """Point forecast on the natural scale."""
    y = model.predict(rows[model.ei_features].to_numpy(dtype=float)) + offset(model, rows)
    return _spec(spec).from_y(y, row_offset(rows))


def to_logit(p, spec: TargetSpec | None = None) -> np.ndarray:
    """Natural scale → model scale (logit of clipped positivity for influenza)."""
    return _spec(spec).to_y(p)


def interval(point_y, half, spec: TargetSpec | None = None) -> tuple[np.ndarray, np.ndarray]:
    return _spec(spec).interval(point_y, half)
