from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.queries.geo import countries_geojson, countries_version

router = APIRouter(prefix="/geo", tags=["geo"])

_cache: dict[str, str] = {}  # version -> GeoJSON text (boundaries change rarely)


@router.get(
    "/countries",
    summary="Country boundaries (GeoJSON, simplified for display)",
    response_class=Response,
    responses={200: {"content": {"application/geo+json": {}}}, 304: {"description": "Unchanged"}},
)
def countries(request: Request, session: Session = Depends(get_session)) -> Response:
    version = countries_version(session)
    etag = f'"{version}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=3600"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    if version not in _cache:
        _cache.clear()
        _cache[version] = countries_geojson(session)
    return Response(_cache[version], media_type="application/geo+json", headers=headers)
