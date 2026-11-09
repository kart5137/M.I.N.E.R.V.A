from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import ResponseMeta, WindowInfo


class DetectionRunInfo(BaseModel):
    run_key: str
    reference_week: date
    finished_at: datetime | None


class AnomalyItem(BaseModel):
    iso3: str
    name: str
    who_region: str | None
    week_start: date
    method: str
    observed: float
    expected: float | None
    upper_band: float | None
    score: float
    ewma: float | None
    ewma_limit: float | None
    specimens_tested: int | None
    severity: str | None
    is_provisional: bool


class AnomalyCountry(BaseModel):
    """Seasonal-EWMA anomalies of one country within the window."""

    iso3: str
    weeks_flagged: int
    latest_week: date
    max_severity: str
    max_score: float


class Anomalies(BaseModel):
    meta: ResponseMeta
    run: DetectionRunInfo | None
    window: WindowInfo
    region: str | None
    iso3: str | None
    method_note: str
    items: list[AnomalyItem]
    by_country: list[AnomalyCountry]


class LocalStat(BaseModel):
    stat_value: float
    z_score: float
    p_value: float
    p_fdr: float
    classification: str


class HotspotItem(BaseModel):
    iso3: str
    name: str
    who_region: str | None
    value: float
    n_neighbours: int
    neighbour_source: str
    gi_star: LocalStat
    local_moran: LocalStat


class Hotspots(BaseModel):
    meta: ResponseMeta
    run: DetectionRunInfo | None
    window: WindowInfo | None
    region: str | None
    available_from: date | None
    available_to: date | None
    weights_spec: str | None
    permutations: int
    fdr_alpha: float
    items: list[HotspotItem]


class HistoryPoint(BaseModel):
    week_start: date
    hot: int
    cold: int
    participants: int
    anomalies: int
    is_provisional: bool


class DetectionHistory(BaseModel):
    meta: ResponseMeta
    region: str | None
    points: list[HistoryPoint]


class ThresholdLevels(BaseModel):
    season: str
    season_start: date
    method: str
    epidemic_threshold: float
    post_threshold: float | None
    medium: float
    high: float
    very_high: float
    n_seasons_used: int
    seasons_used: list[str]
    quality_note: str | None


class RiskItem(BaseModel):
    iso3: str
    name: str
    who_region: str | None
    assessed_week: date
    target_week: date
    risk_level: str
    rule: str
    forecast_point: float
    forecast_lo80: float | None
    forecast_hi80: float | None
    model_type: str
    thresholds: ThresholdLevels


class NotAssessed(BaseModel):
    iso3: str
    name: str
    reason: str


class RiskList(BaseModel):
    meta: ResponseMeta
    run: DetectionRunInfo | None
    region: str | None
    rule: str
    items: list[RiskItem]
    not_assessed: list[NotAssessed]


class HotspotStatus(BaseModel):
    window_end: date
    value: float
    gi_star: LocalStat
    local_moran: LocalStat
    n_neighbours: int
    neighbour_source: str


class CountryDetection(BaseModel):
    meta: ResponseMeta
    run: DetectionRunInfo | None
    iso3: str
    thresholds: ThresholdLevels | None
    thresholds_reason: str | None
    risk: RiskItem | None
    anomalies: list[AnomalyItem]
    hotspots: list[HotspotStatus]
