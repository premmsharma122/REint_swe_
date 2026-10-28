"""FastAPI app: JSON API under /api, and (in Docker) serves the built React app at /."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import analysis, config, store

app = FastAPI(title="Wind Forecast Monitor", version="1.0.0")


def _check_dates(start: str, end: str):
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise HTTPException(400, "Dates must be YYYY-MM-DD")
    lo, hi = date.fromisoformat(config.SCOPE_START), date.fromisoformat(config.SCOPE_END)
    if s > e or s < lo or e > hi:
        raise HTTPException(400, f"Range must be within {lo} .. {hi} and start <= end")


@app.get("/api/health")
def health():
    d = store.get()
    return {"status": "ok", "source": d["source"], "scope": [config.SCOPE_START, config.SCOPE_END],
            "actual_hours": len(d["actuals"]), "forecast_rows": len(d["forecasts"]),
            "max_horizon_h": config.MAX_HORIZON_H, "default_cutoff_hour": config.DEFAULT_CUTOFF_HOUR}


@app.get("/api/forecast-vs-actual")
def forecast_vs_actual(start: str = config.SCOPE_START, end: str = config.SCOPE_END,
                       horizon: float = Query(24, ge=0, le=config.MAX_HORIZON_H)):
    """Hourly actual vs the latest forecast that was published >= `horizon` hours before each target."""
    _check_dates(start, end)
    d = store.get()
    p = analysis.paired(d["forecasts"], d["actuals"], start, end, horizon)
    return {"horizon_h": horizon, "metrics": analysis.metrics(p),
            "rows": analysis.records(p[["startTime", "publishTime", "horizon_h", "forecast", "actual", "error"]])}


@app.get("/api/metrics")
def get_metrics(start: str = config.SCOPE_START, end: str = config.SCOPE_END,
                horizon: float = Query(24, ge=0, le=config.MAX_HORIZON_H)):
    """Headline metrics at `horizon`, error-vs-horizon curve, and error by hour of day."""
    _check_dates(start, end)
    d = store.get()
    p = analysis.paired(d["forecasts"], d["actuals"], start, end, horizon)
    return {"horizon_h": horizon, "summary": analysis.metrics(p),
            "by_horizon": analysis.error_by_horizon(d["forecasts"], d["actuals"], start, end, config.MAX_HORIZON_H),
            "by_hour": analysis.error_by_hour_of_day(p)}


@app.get("/api/day-ahead")
def day_ahead(delivery_date: str, cutoff_hour: int = Query(config.DEFAULT_CUTOFF_HOUR, ge=0, le=23)):
    """The forecast the trader sees at decision time (D-1, cutoff_hour UTC) for delivery day D."""
    _check_dates(delivery_date, delivery_date)
    d = store.get()
    return analysis.day_ahead_view(d["forecasts"], d["actuals"], delivery_date, cutoff_hour)


# ---- static React build (present only inside the Docker image) -------------------------------
STATIC = Path(__file__).resolve().parent.parent / "static"
if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        f = STATIC / full_path
        return FileResponse(f if f.is_file() else STATIC / "index.html")
