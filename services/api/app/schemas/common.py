from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    key: str
    name: str
    attribution: str | None


class ResponseMeta(BaseModel):
    """Data-availability context returned with every surveillance response."""

    disease: str
    first_week: date
    reference_week: date = Field(
        description="Last week with near-complete reporting; later weeks are provisional."
    )
    provisional_from: date | None
    latest_week: date
    sources: list[SourceRef]
    demo: bool = False


class WindowInfo(BaseModel):
    start: date
    end: date
    weeks: int
    includes_provisional: bool
