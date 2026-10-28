"""Loads data once and keeps it in memory. Order of preference:
1. USE_SAMPLE_DATA=1  -> synthetic data (offline)
2. data/*.json cache  -> committed snapshot of the real Elexon data (fast, works on Vercel/Heroku)
3. live Elexon fetch  -> then writes the cache
"""
from __future__ import annotations

import logging
import threading

import pandas as pd

from . import analysis, config

log = logging.getLogger(__name__)
_lock = threading.Lock()
_state: dict = {}

ACT_FILE = config.DATA_DIR / "wind_actuals_fuelhh.json"
FC_FILE = config.DATA_DIR / "wind_forecasts_windfor.json"


def refresh_cache() -> None:
    from . import elexon
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    elexon.fetch_actuals(config.SCOPE_START, config.SCOPE_END).to_json(ACT_FILE, orient="records")
    elexon.fetch_forecasts(config.SCOPE_START, config.SCOPE_END).to_json(FC_FILE, orient="records")


def get() -> dict:
    with _lock:
        if _state:
            return _state
        if config.USE_SAMPLE_DATA:
            from .sample import make_sample
            raw_a, raw_f = make_sample(config.SCOPE_START, config.SCOPE_END, config.FORECAST_LEAD_IN_DAYS)
            source = "sample"
        else:
            if not (ACT_FILE.exists() and FC_FILE.exists()):
                log.info("No cache found - fetching from Elexon")
                refresh_cache()
            raw_a, raw_f = pd.read_json(ACT_FILE), pd.read_json(FC_FILE)
            source = "elexon"
        act30 = analysis.clean_actuals(raw_a)
        fc = analysis.clean_forecasts(raw_f)
        s = pd.Timestamp(config.SCOPE_START, tz="UTC")
        e = pd.Timestamp(config.SCOPE_END, tz="UTC") + pd.Timedelta(days=1)
        act30 = act30[(act30["startTime"] >= s) & (act30["startTime"] < e)]
        fc = fc[(fc["startTime"] >= s) & (fc["startTime"] < e)]       # targets in January only
        fc = fc[(fc["horizon_h"] >= 0) & (fc["horizon_h"] <= config.MAX_HORIZON_H)]
        _state.update(source=source, actuals_30m=act30, actuals=analysis.hourly_actuals(act30), forecasts=fc)
        return _state
