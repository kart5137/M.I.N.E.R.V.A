"""Integration tests: ingestion into a real (test) PostGIS database."""

from __future__ import annotations

import json

from sqlalchemy import text

from conftest import make_raw
from ei_pipeline.catalog import seed_reference
from ei_pipeline.db import session_scope
from ei_pipeline.ingest.boundaries import ingest_boundaries
from ei_pipeline.ingest.flunet import ingest_flunet

TODAY = "2025-06-01"

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
ISLAND = {"type": "Polygon", "coordinates": [[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]]}


def _feature(code, adm0, name, geom, iso_eh=None):
    return {"type": "Feature", "geometry": geom, "properties": {
        "ISO_A3_EH": iso_eh or code, "ADM0_A3": adm0, "ISO_A2_EH": "-99", "NAME": name,
        "NAME_LONG": name, "CONTINENT": "Test", "LABEL_X": 0.5, "LABEL_Y": 0.5}}


def _seed(engine):
    with session_scope(engine) as s:
        seed_reference(s)


def _q(engine, sql, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).scalar()


def test_flunet_ingest_is_idempotent_and_records_revisions(db, tmp_path):
    _seed(db)
    raw = make_raw(weeks=40, countries=("ARG", "BRA", "X09", "X10"), drop_last=2)
    path = tmp_path / "flunet.csv"
    raw.to_csv(path, index=False)

    first = ingest_flunet(db, path=path, today=TODAY)
    # ARG reports all 40 weeks; BRA and GBR (= X09 + X10) lag by 2 weeks.
    assert first["inserted"] == 40 + 38 + 38
    assert first["revisions_recorded"] == 0
    assert _q(db, "SELECT count(*) FROM countries") == 3          # ARG, BRA, GBR
    assert _q(db, "SELECT count(*) FROM country_code_aliases") == 4
    assert _q(db, "SELECT count(*) FROM surveillance_weekly WHERE is_provisional") == 2

    second = ingest_flunet(db, path=path, today=TODAY)
    assert (second["inserted"], second["updated"], second["revisions_recorded"]) == (0, 0, 0)
    assert second["unchanged"] == first["inserted"]

    # Source revises one week for ARG.
    raw.loc[(raw.COUNTRY_CODE == "ARG") & (raw.ISO_WEEK == 10), "SPEC_PROCESSED_NB"] = 999
    raw.to_csv(path, index=False)
    third = ingest_flunet(db, path=path, today=TODAY)
    assert (third["updated"], third["revisions_recorded"]) == (1, 1)
    prev = _q(db, "SELECT previous_values FROM surveillance_revisions")
    assert prev["specimens_tested"] == 100 + 9  # value before the revision
    assert _q(db, "SELECT count(*) FROM ingestion_runs WHERE status = 'succeeded'") == 3


def test_failed_run_is_recorded(db, tmp_path):
    _seed(db)
    path = tmp_path / "broken.csv"
    path.write_text("not,a,flunet,file\n1,2,3,4\n")
    try:
        ingest_flunet(db, path=path, today=TODAY)
    except KeyError:
        pass
    assert _q(db, "SELECT status FROM ingestion_runs") == "failed"
    assert _q(db, "SELECT surveillance_weekly_count FROM (SELECT count(*) AS "
                  "surveillance_weekly_count FROM surveillance_weekly) x") == 0


def test_boundaries_merge_features_and_alias_kosovo(db, tmp_path):
    _seed(db)
    path = tmp_path / "ne.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        _feature("AUS", "AUS", "Australia", SQUARE),
        _feature("AUS", "ATC", "Ashmore and Cartier Is.", ISLAND),
        _feature("KOS", "KOS", "Kosovo", ISLAND, iso_eh="-99"),
    ]}))
    report = ingest_boundaries(db, path=path)
    assert report["inserted"] == 2 and report["features_merged_by_code"] == {"AUS": 2}
    assert _q(db, "SELECT name FROM countries WHERE iso3 = 'AUS'") == "Australia"
    assert _q(db, "SELECT ST_NumGeometries(geom) FROM countries WHERE iso3 = 'AUS'") == 2
    assert _q(db, "SELECT iso3 FROM country_code_aliases WHERE alias = 'KOS'") == "XKX"
    assert ingest_boundaries(db, path=path)["unchanged"] == 2
