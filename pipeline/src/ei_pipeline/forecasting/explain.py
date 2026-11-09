"""SHAP explanations for tree models (values on the model's logit scale)."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import shap

from ei_pipeline.forecasting import config as cfg
from ei_pipeline.forecasting.features import FEATURES

log = logging.getLogger(__name__)


def explain(model, rows: pd.DataFrame) -> tuple[np.ndarray, float]:
    """(SHAP matrix rows × features, expected value)."""
    X = rows[FEATURES].to_numpy(dtype=float)
    explainer = shap.TreeExplainer(model)
    values = np.asarray(explainer.shap_values(X, check_additivity=False))
    base = float(np.ravel(explainer.expected_value)[0])
    return values, base


def top_contributors(values: np.ndarray, rows: pd.DataFrame,
                     k: int = cfg.TOP_K_EXPLANATIONS) -> list[list[dict]]:
    X = rows[FEATURES].to_numpy(dtype=float)
    out = []
    for i in range(len(rows)):
        order = np.argsort(-np.abs(values[i]))[:k]
        out.append([
            {"feature": FEATURES[j], "shap_value": float(values[i, j]),
             "feature_value": None if np.isnan(X[i, j]) else float(X[i, j]), "rank": r + 1}
            for r, j in enumerate(order)
        ])
    return out


def global_importance(values: np.ndarray) -> dict[str, float]:
    mean_abs = np.abs(values).mean(axis=0)
    return {f: float(v) for f, v in sorted(zip(FEATURES, mean_abs, strict=True),
                                           key=lambda t: -t[1])}
