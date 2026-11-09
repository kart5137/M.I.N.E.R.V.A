"""Model factory. ML models predict logit positivity; baselines are read from the frame."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor

from ei_pipeline.forecasting import config as cfg
from ei_pipeline.forecasting.data import expit, logit
from ei_pipeline.forecasting.features import FEATURES

#: Point forecasts are clipped to this range before converting to logit (conformal).
P_CLIP = (0.001, 0.999)


def make_model(name: str, hp: cfg.Hyperparams):
    if name == "random_forest":
        return RandomForestRegressor(**hp.rf)
    if name == "xgboost":
        return XGBRegressor(**hp.xgb)
    raise ValueError(name)


def training_rows(frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Rows whose target week is known by `cutoff` and usable as a target."""
    return frame[(frame["target_week"] <= cutoff) & frame["trainable"]
                 & (frame["target_week"] >= pd.Timestamp(cfg.TRAIN_START))]


def fit(name: str, frame: pd.DataFrame, cutoff: pd.Timestamp, hp: cfg.Hyperparams):
    rows = training_rows(frame, cutoff)
    model = make_model(name, hp)
    model.fit(rows[FEATURES].to_numpy(dtype=float), rows["actual_y"].to_numpy(dtype=float))
    return model, rows


def predict_p(model, rows: pd.DataFrame) -> np.ndarray:
    return expit(model.predict(rows[FEATURES].to_numpy(dtype=float)))


def to_logit(p) -> np.ndarray:
    return logit(np.clip(np.asarray(p, dtype=float), *P_CLIP))


def interval(point_y, half) -> tuple[np.ndarray, np.ndarray]:
    """Bounds on the positivity scale. A bound that reaches the clip range becomes 0 or 1,
    so weeks with 0% (or 100%) positivity can be covered."""
    lo = expit(np.asarray(point_y) - np.asarray(half))
    hi = expit(np.asarray(point_y) + np.asarray(half))
    return (np.where(lo <= P_CLIP[0] * 1.0001, 0.0, lo),
            np.where(hi >= P_CLIP[1] * 0.9999, 1.0, hi))
