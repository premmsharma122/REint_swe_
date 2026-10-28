"""Thin client for the Elexon BMRS 'stream' endpoints (no API key required)."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from . import config

log = logging.getLogger(__name__)


def _get(path: str, params: dict, retries: int = 3) -> list[dict]:
    url = f"{config.ELEXON_BASE_URL}{path}"
    for attempt in range(retries):
        r = requests.get(url, params=params, headers={"accept": "application/json"}, timeout=config.HTTP_TIMEOUT)
        if r.status_code == 429 or r.status_code >= 500:   # rate limited / transient -> back off
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Elexon API failed after {retries} attempts: {url} {params}")


def _chunks(start: datetime, end: datetime, days: int):
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=days), end)
        yield cur, nxt
        cur = nxt


def fetch_actuals(start: str, end: str) -> pd.DataFrame:
    """FUELHH, fuelType=WIND, by settlement date (inclusive). NB: settlement-date params
    cannot be combined with publishDateTime params (the API returns 400)."""
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end) + timedelta(days=1)
    rows = []
    for a, b in _chunks(s, e, config.CHUNK_DAYS):
        rows += _get("/datasets/FUELHH/stream", {
            "settlementDateFrom": a.strftime("%Y-%m-%d"),
            "settlementDateTo": (b - timedelta(days=1)).strftime("%Y-%m-%d"),
            "fuelType": "WIND",
        })
    return pd.DataFrame(rows)


def fetch_forecasts(start: str, end: str, lead_in_days: int = config.FORECAST_LEAD_IN_DAYS) -> pd.DataFrame:
    """WINDFOR by publish time. We start `lead_in_days` early so that 1 Jan targets still
    have forecasts with a 24-48h horizon."""
    s = datetime.fromisoformat(start).replace(tzinfo=timezone.utc) - timedelta(days=lead_in_days)
    e = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=1)
    rows = []
    for a, b in _chunks(s, e, config.CHUNK_DAYS):
        rows += _get("/datasets/WINDFOR/stream", {
            "publishDateTimeFrom": a.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "publishDateTimeTo": b.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    return pd.DataFrame(rows)
