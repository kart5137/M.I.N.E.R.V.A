"""ORM models. M1 covers reference and observation tables; model/output tables arrive
with their milestones (M5–M7), each with its own migration."""

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
