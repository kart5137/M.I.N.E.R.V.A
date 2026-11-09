"""Reference catalogues shared by the pipeline (what to load) and the API (how to label)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorSpec:
    code: str
    label: str
    unit: str
    group: str  # "health_system" | "population"


#: World Bank WDI indicators loaded into `health_indicators` (CC BY 4.0).
HEALTH_INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec("SH.MED.BEDS.ZS", "Hospital beds", "per 1,000 people", "health_system"),
    IndicatorSpec("SH.MED.PHYS.ZS", "Physicians", "per 1,000 people", "health_system"),
    IndicatorSpec("SH.MED.NUMW.P3", "Nurses and midwives", "per 1,000 people", "health_system"),
    IndicatorSpec("SH.XPD.CHEX.GD.ZS", "Current health expenditure", "% of GDP",
                  "health_system"),
    IndicatorSpec("SP.POP.65UP.TO.ZS", "Population aged 65+", "% of population", "population"),
)

HEALTH_INDICATOR_BY_CODE = {i.code: i for i in HEALTH_INDICATORS}
