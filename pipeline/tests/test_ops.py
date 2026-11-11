"""Operational paths (M8): population ingest, the download helper, and the `ei` CLI
including the weekly job's step order and failure behaviour. No network access."""

from __future__ import annotations

import json

import pytest
import requests
from sqlalchemy import text

from conftest import make_raw
from ei_pipeline import cli, util
from ei_pipeline.catalog import seed_reference
from ei_pipeline.db import session_scope
from ei_pipeline.ingest.flunet import ingest_flunet
from ei_pipeline.ingest.population import ingest_population


def _wb(path, rows):
    meta = {"page": 1, "pages": 1, "lastupdated": "2026-10-08"}
    data = [{"indicator": {"id": "SP.POP.TOTL"}, "countryiso3code": iso, "date": str(y),
             "value": v} for iso, y, v in rows]
    path.write_text(json.dumps([meta, data]), encoding="utf-8")


def test_population_ingest(db, tmp_path):
    with session_scope(db) as s:
        seed_reference(s)
    path = tmp_path / "pop.json"
    _wb(path, [("ARG", 2023, 46_000_000)])
    with pytest.raises(RuntimeError, match="countries"):
        ingest_population(db, path=path)  # no countries yet
    flu = tmp_path / "flunet.csv"
    make_raw(weeks=3, countries=("ARG", "BRA")).to_csv(flu, index=False)
    ingest_flunet(db, path=flu, today="2025-06-01")
    _wb(path, [("ARG", 2023, 46_000_000), ("ARG", 2024, 46_500_000), ("ARG", 2025, None),
               ("WLD", 2024, 8_000_000_000)])
    first = ingest_population(db, path=path)
    assert (first["inserted"], first["latest_year"]) == (2, 2024)
    assert first["codes_skipped_not_in_countries"] == ["WLD"]
    assert first["countries_without_population"] == ["BRA"]

    _wb(path, [("ARG", 2023, 46_000_000), ("ARG", 2024, 46_600_000)])
    second = ingest_population(db, path=path)
    assert (second["inserted"], second["updated"], second["unchanged"]) == (0, 1, 1)
    with db.connect() as c:
        assert c.execute(text("SELECT population FROM population_annual WHERE year = 2024"
                              )).scalar() == 46_600_000


class _Resp:
    def __init__(self, chunks, status=200):
        self.chunks, self.status = chunks, status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"HTTP {self.status}")

    def iter_content(self, chunk_size):
        yield from self.chunks


def test_download_retries_then_writes_atomically(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        if len(calls) == 1:
            raise requests.ConnectionError("reset")
        return _Resp([b"ab", b"cd"])

    monkeypatch.setattr(util.requests, "get", fake_get)
    monkeypatch.setattr(util.time, "sleep", lambda s: None)
    dest = tmp_path / "sub" / "file.csv"
    assert util.download("http://x", dest) == dest
    assert dest.read_bytes() == b"abcd" and len(calls) == 2
    assert not dest.with_suffix(".csv.part").exists()
    assert util.sha256_file(dest) == (
        "88d4266fd4e6338d13b845fcf289579d209c897823b9217da3e161936f031589")


def test_download_gives_up_and_keeps_previous_file(tmp_path, monkeypatch):
    dest = tmp_path / "file.csv"
    dest.write_bytes(b"old")
    monkeypatch.setattr(util.requests, "get", lambda url, **kw: _Resp([], status=503))
    monkeypatch.setattr(util.time, "sleep", lambda s: None)
    with pytest.raises(requests.HTTPError):
        util.download("http://x", dest, retries=2)
    assert dest.read_bytes() == b"old"


@pytest.fixture
def fake_jobs(monkeypatch):
    """Replace every job the CLI runs with a recorder."""
    calls: list[tuple] = []

    def step(name, out):
        def run(*args, **kw):
            calls.append((name, kw))
            if isinstance(out, Exception):
                raise out
            return out
        return run

    monkeypatch.setattr(cli, "make_engine", lambda: "ENGINE")
    monkeypatch.setattr(cli, "_run_step", lambda engine, s, refresh, **opts: (
        calls.append((s, {"refresh": refresh, **opts})) or {"inserted": 1}))
    import ei_pipeline.detection.run as det
    import ei_pipeline.forecasting.run as fc
    monkeypatch.setattr(fc, "run_forecast", step("forecast", {"run_key": "k", "x": 1}))
    monkeypatch.setattr(det, "run_detection", step("detect", {"alerts": 3}))
    monkeypatch.setattr(cli, "prune_runs", step("prune", {"older_runs": 0}))
    return calls


def test_weekly_runs_every_step_in_order(fake_jobs, capsys):
    assert cli.main(["weekly", "--fast", "--keep", "4"]) == 0
    names = [c[0] for c in fake_jobs]
    # Influenza is forecast and scanned before dengue (D4).
    assert cli.DISEASES == ("influenza", "dengue")
    assert names == [*cli.STEPS, "forecast", "detect", "forecast", "detect", "prune"]
    # Only surveillance sources are re-downloaded; others are fetched only when missing.
    assert cli.REFRESHED == ("flunet", "dengue", "malaria", "cholera", "covid")
    assert [c[1]["refresh"] for c in fake_jobs[:len(cli.STEPS)]] == [
        s in cli.REFRESHED for s in cli.STEPS]
    # Weather history is the backfill workflow's job; the weekly run only tops up.
    assert dict(fake_jobs[:len(cli.STEPS)])["weather"] == {"refresh": False, "topup_only": True}
    assert fake_jobs[-5][1] == {"disease": "influenza", "fast": True}
    assert fake_jobs[-3][1] == {"disease": "dengue", "fast": True}
    out = capsys.readouterr().out
    assert '[forecast:influenza]' in out and '[detect:dengue]' in out
    assert '"run_key": "k"' in out and '"x"' not in out


def test_weekly_stops_on_failure(fake_jobs, monkeypatch):
    import ei_pipeline.forecasting.run as fc

    def boom(*a, **k):
        raise RuntimeError("model failed")

    monkeypatch.setattr(fc, "run_forecast", boom)
    with pytest.raises(RuntimeError, match="model failed"):
        cli.main(["weekly"])
    assert "detect" not in [c[0] for c in fake_jobs]


def test_weekly_continues_when_optional_weather_fails(fake_jobs, monkeypatch):
    real = cli._run_step

    def run_step(engine, s, refresh, **opts):
        if s == "weather":
            raise RuntimeError("Open-Meteo down")
        return real(engine, s, refresh, **opts)

    monkeypatch.setattr(cli, "_run_step", run_step)
    assert cli.OPTIONAL == ("malaria", "cholera", "covid", "weather")
    assert cli.main(["weekly"]) == 0
    assert [c[0] for c in fake_jobs][-5:] == ["forecast", "detect", "forecast", "detect",
                                              "prune"]


def test_ingest_weather_passes_budget_options(fake_jobs):
    assert cli.main(["ingest", "weather", "--budget", "100", "--backfill-only",
                     "--max-minutes", "25"]) == 0
    assert fake_jobs == [("weather", {"refresh": False, "budget": 100.0,
                                      "backfill_only": True, "topup_only": False,
                                      "max_minutes": 25.0})]


def test_cli_single_commands(fake_jobs, capsys):
    assert cli.main(["ingest", "all"]) == 0
    assert [c[0] for c in fake_jobs] == list(cli.STEPS)
    assert cli.main(["prune", "--keep", "3"]) == 0
    assert cli.main(["detect", "run"]) == 0
    assert cli.main(["forecast", "run", "--fast", "--disease", "dengue"]) == 0
    out = capsys.readouterr().out
    assert "[prune]" in out and "[detect:influenza]" in out and "[detect:dengue]" in out
    assert "[forecast:dengue]" in out and "[forecast:influenza]" not in out
    assert fake_jobs[-1] == ("forecast", {"disease": "dengue", "fast": True})


def test_summary_flattens_reports():
    report = {"inserted": 2, "noise": 1, "validation": {"rows_excluded": 4},
              "countries_without_population": ["A", "B"],
              "indicators": {"x": {"countries_with_value": 9}}}
    assert cli._summary(report) == {"inserted": 2, "rows_excluded": 4,
                                    "countries_without_population": 2,
                                    "indicators": {"x": 9}}


GOOD = 'A,B,C\r\n1,"x, with comma",3\r\n4,"two\r\nlines",6\r\n'
SPLICED = 'A,B,C\r\n1,2,3,4,5\r\n4,5\r\n'  # spliced record + truncated last record


def test_flunet_structure_check(tmp_path):
    from ei_pipeline.sources.flunet import check_structure

    p = tmp_path / "f.csv"
    p.write_bytes(GOOD.encode())
    assert check_structure(p) is None  # quoted commas and line breaks are fine
    p.write_bytes(SPLICED.encode())
    assert check_structure(p) == ("2 record(s) without 3 fields (record 2: 5 fields, "
                                  "record 3: 2 fields)")
    p.write_bytes(b"")
    assert check_structure(p) == "empty file"


def test_flunet_download_tries_variants_and_keeps_good_file(tmp_path, monkeypatch):
    from ei_pipeline import util
    from ei_pipeline.sources import flunet

    served: list[dict] = []

    def fake(url, dest, *, headers):
        served.append(headers)
        dest.write_bytes((SPLICED if len(served) == 1 else GOOD).encode())
        return dest

    monkeypatch.setattr(util, "download", fake)
    dest = tmp_path / "VIW_FNT.csv"
    assert flunet.download(dest) == dest and dest.read_bytes() == GOOD.encode()
    assert served == list(flunet.DOWNLOAD_VARIANTS[:2])
    assert [p.name for p in tmp_path.iterdir()] == ["VIW_FNT.csv"]  # temp file removed

    # Every variant malformed: fail loudly and keep the previous good file.
    monkeypatch.setattr(util, "download",
                        lambda url, d, *, headers: d.write_bytes(SPLICED.encode()))
    with pytest.raises(flunet.MalformedExport, match="previous file kept"):
        flunet.download(dest)
    assert dest.read_bytes() == GOOD.encode()
