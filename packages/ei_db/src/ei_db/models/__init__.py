"""ORM models. M1 covers reference and observation tables; model/output tables arrive
with their milestones (M5–M7), each with its own migration."""

from ei_db.models.detection import (
    Anomaly,
    DetectionRun,
    HotspotResult,
    RiskAssessment,
    SeasonalThreshold,
)
from ei_db.models.ml import (
    BacktestPrediction,
    Forecast,
    ForecastExplanation,
    ModelEvaluation,
    ModelVersion,
)
from ei_db.models.observations import (
    CoverageProfile,
    HealthIndicator,
    PopulationAnnual,
    SurveillanceRevision,
    SurveillanceWeekly,
)
from ei_db.models.reference import (
    Country,
    CountryCodeAlias,
    DataSource,
    Disease,
    IngestionRun,
)

__all__ = [
    "Anomaly",
    "DetectionRun",
    "HotspotResult",
    "RiskAssessment",
    "SeasonalThreshold",
    "BacktestPrediction",
    "Forecast",
    "ForecastExplanation",
    "ModelEvaluation",
    "ModelVersion",
    "Country",
    "CountryCodeAlias",
    "CoverageProfile",
    "DataSource",
    "Disease",
    "HealthIndicator",
    "IngestionRun",
    "PopulationAnnual",
    "SurveillanceRevision",
    "SurveillanceWeekly",
]
