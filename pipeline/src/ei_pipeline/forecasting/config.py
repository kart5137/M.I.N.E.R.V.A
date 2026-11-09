"""Forecasting settings (docs/DESIGN.md §6.2). Change here, not in code."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

HORIZONS: tuple[int, ...] = (1, 2, 4)
TARGET = "positivity"
ELIGIBLE_TIERS: tuple[str, ...] = ("A", "B")

#: Rows before this are loaded only so that 52-week seasonal features exist.
HISTORY_START = date(2013, 1, 7)
#: First target week used for training.
TRAIN_START = date(2014, 9, 29)
#: COVID-19 disruption: target weeks inside are excluded from training and evaluation.
COVID_START, COVID_END = date(2020, 3, 1), date(2022, 6, 30)
#: A weekly positivity counts only with at least this many specimens.
MIN_TESTS = 10

#: Rolling-origin backtest: origins every ORIGIN_STEP weeks from BACKTEST_START.
BACKTEST_START = date(2024, 10, 7)
ORIGIN_STEP = 2
#: ML models are refitted every REFIT_EVERY weeks during the backtest (expanding window).
REFIT_EVERY = 8

#: Conformal intervals: calibrate on residuals from origins strictly before the one being
#: evaluated; need at least this many earlier origins.
CONFORMAL_MIN_ORIGINS = 6
INTERVAL_LEVELS = (0.80, 0.95)
#: Floor for the volatility scale (logit units) used to normalise conformal scores.
SCALE_FLOOR = 0.30
#: Mondrian conformal: quantiles are calibrated separately per testing-volume group
#: (mean specimens/week over the 4 weeks to the origin). Low-volume positivity is
#: dominated by sampling noise; pooling it would widen every country's interval.
CONFORMAL_GROUP_EDGES = (50, 200, 1000)
#: A group needs this many calibration scores; otherwise all groups are pooled.
CONFORMAL_MIN_GROUP = 30

#: SHAP contributors stored per forecast.
TOP_K_EXPLANATIONS = 8

BASELINES = ("seasonal_naive", "last_value", "moving_average_4")
ML_MODELS = ("random_forest", "xgboost")
REFERENCE_BASELINE = "seasonal_naive"


@dataclass(frozen=True)
class Hyperparams:
    rf: dict = field(default_factory=lambda: {
        "n_estimators": 200, "max_depth": 12, "min_samples_leaf": 10,
        "max_features": 0.5, "n_jobs": -1, "random_state": 42,
    })
    xgb: dict = field(default_factory=lambda: {
        "n_estimators": 500, "learning_rate": 0.04, "max_depth": 5,
        "min_child_weight": 10, "subsample": 0.8, "colsample_bytree": 0.8,
        "reg_lambda": 1.0, "tree_method": "hist", "n_jobs": -1, "random_state": 42,
    })


#: Smaller settings for tests (`ei forecast run --fast`).
FAST = Hyperparams(
    rf={"n_estimators": 30, "max_depth": 8, "min_samples_leaf": 5, "max_features": 0.5,
        "n_jobs": -1, "random_state": 42},
    xgb={"n_estimators": 60, "learning_rate": 0.1, "max_depth": 4, "min_child_weight": 5,
         "subsample": 0.9, "colsample_bytree": 0.9, "tree_method": "hist", "n_jobs": -1,
         "random_state": 42},
)
