"""Open-Meteo Historical Weather API, ERA5 reanalysis only (docs/datasets/weather.md).

Daily mean 2 m temperature, precipitation sum and mean 2 m relative humidity for one
point. `models=era5` pins a single, temporally consistent reanalysis (the default "best
match" blends in other models for recent days). Days are in the point's local time zone.

Free use is limited by *weighted* calls: a request counts max(1, days / 14) calls (three
variables count as one), with limits of 600 per minute, 5,000 per hour and 10,000 per
day. `Quota` keeps a run inside the minute and hour limits and a per-run budget."""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests

from ei_pipeline.config import USER_AGENT

log = logging.getLogger(__name__)

API_URL = "https://archive-api.open-meteo.com/v1/archive"
#: API variable → our column.
VARIABLES = {"temperature_2m_mean": "temperature", "precipitation_sum": "precipitation",
             "relative_humidity_2m_mean": "humidity"}
MODEL = "era5"
#: Requests cover at most this many days (52 weeks), so one request weighs 26 calls.
MAX_DAYS = 364


class QuotaExhausted(RuntimeError):
    """The hourly/daily API limit, or this run's budget, is used up. Not an error: the
    next run continues where this one stopped."""


class RequestRejected(ValueError):
    """The API refused the request (4xx other than rate limiting)."""


def weight(start: date, end: date) -> float:
    """Weighted API calls for one request of `start`–`end` inclusive (≤ 10 variables)."""
    return max(1.0, ((end - start).days + 1) / 14)


class Quota:
    """Client-side pacing: sliding-window minute and hour limits (kept below the API's,
    which other users of a shared IP also draw on) and a total budget for the run."""

    def __init__(self, budget: float, per_minute: float = 500, per_hour: float = 4500,
                 clock=time.monotonic, sleep=time.sleep):
        self.budget, self.used = budget, 0.0
        self.limits = ((60.0, per_minute), (3600.0, per_hour))
        self.log: deque[tuple[float, float]] = deque()
        self.clock, self.sleep = clock, sleep

    def take(self, w: float) -> None:
        if self.used + w > self.budget:
            raise QuotaExhausted(f"run budget of {self.budget:.0f} weighted calls used")
        while True:
            now = self.clock()
            while self.log and now - self.log[0][0] > 3600:
                self.log.popleft()
            wait = 0.0
            for span, cap in self.limits:
                recent = [(t, x) for t, x in self.log if now - t < span]
                if sum(x for _, x in recent) + w > cap:
                    if span > 60:  # hour limit: let a later run continue
                        raise QuotaExhausted("hourly pacing limit reached")
                    wait = max(wait, span - (now - recent[0][0]) + 0.5)
            if wait == 0:
                break
            self.sleep(wait)
        self.log.append((self.clock(), w))
        self.used += w


@dataclass(frozen=True)
class PointSeries:
    lat: float
    lon: float
    elevation_m: float | None
    #: Columns: date (datetime64), temperature, precipitation, humidity; NaN = missing.
    daily: pd.DataFrame


def parse(payload: dict) -> PointSeries:
    daily = payload.get("daily") or {}
    missing = [v for v in ("time", *VARIABLES) if v not in daily]
    if missing:
        raise ValueError(f"Open-Meteo response lacks {missing}: {payload.get('reason')}")
    df = pd.DataFrame({"date": pd.to_datetime(daily["time"])})
    for api_name, col in VARIABLES.items():
        df[col] = pd.to_numeric(pd.Series(daily[api_name], dtype="object"), errors="coerce")
    elev = payload.get("elevation")
    return PointSeries(lat=float(payload["latitude"]), lon=float(payload["longitude"]),
                       elevation_m=None if elev is None or math.isnan(elev) else float(elev),
                       daily=df.sort_values("date", ignore_index=True))


def fetch(lat: float, lon: float, start: date, end: date, *, quota: Quota,
          retries: int = 4, timeout: int = 120) -> PointSeries:
    """Daily ERA5 values for one point, `start`–`end` inclusive (≤ MAX_DAYS days)."""
    if (end - start).days + 1 > MAX_DAYS:
        raise ValueError(f"request spans more than {MAX_DAYS} days")
    query = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
             "start_date": start.isoformat(), "end_date": end.isoformat(),
             "daily": ",".join(VARIABLES), "models": MODEL, "timezone": "auto"}
    quota.take(weight(start, end))
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(API_URL, params=query, timeout=timeout,
                                headers={"User-Agent": USER_AGENT})
            if resp.status_code == 429:
                reason = (resp.json() or {}).get("reason", "") if resp.content else ""
                if "Minutely" not in reason:
                    raise QuotaExhausted(f"Open-Meteo: {reason or 'rate limited'}")
                log.info("Open-Meteo minute limit (shared IP?); waiting 60 s")
                quota.sleep(60)
                continue
            if 400 <= resp.status_code < 500:
                raise RequestRejected(f"Open-Meteo {resp.status_code}: {resp.text[:300]}")
            resp.raise_for_status()
            return parse(resp.json())
        except (QuotaExhausted, RequestRejected):
            raise
        except (requests.RequestException, ValueError) as exc:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            log.warning("Open-Meteo request failed (%.2f, %.2f), retry in %ss: %s",
                        lat, lon, wait, exc)
            quota.sleep(wait)
    raise QuotaExhausted("Open-Meteo minute limit persisted")
