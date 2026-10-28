"""Pure pandas analysis functions (no I/O) so they are easy to unit-test.

Conventions
-----------
* All timestamps are timezone-aware UTC, datetime64[ns, UTC].
* Forecast error = forecast - actual.  Positive => wind was OVER-forecast, i.e. the
  buyer would have under-procured thermal/other power (short position).
* Horizon (hours) = startTime - publishTime, i.e. how far ahead the forecast was made.
* Actuals (FUELHH, 30 min) are averaged into hourly means to match WINDFOR (hourly).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NS_UTC = "datetime64[ns, UTC]"


def _utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True).astype(NS_UTC)


def clean_actuals(raw: pd.DataFrame) -> pd.DataFrame:
    """FUELHH rows -> half-hourly [startTime, generation] for WIND only."""
    if raw.empty:
        return pd.DataFrame({"startTime": pd.Series(dtype=NS_UTC), "generation": pd.Series(dtype=float)})
    df = raw.copy()
    if "fuelType" in df:
        df = df[df["fuelType"] == "WIND"]
    df["startTime"] = _utc(df["startTime"])
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = df.dropna(subset=["generation"]).drop_duplicates("startTime", keep="last")
    return df[["startTime", "generation"]].sort_values("startTime").reset_index(drop=True)


def clean_forecasts(raw: pd.DataFrame) -> pd.DataFrame:
    """WINDFOR rows -> [publishTime, startTime, generation, horizon_h]."""
    if raw.empty:
        return pd.DataFrame({"publishTime": pd.Series(dtype=NS_UTC), "startTime": pd.Series(dtype=NS_UTC),
                             "generation": pd.Series(dtype=float), "horizon_h": pd.Series(dtype=float)})
    df = raw.copy()
    df["publishTime"] = _utc(df["publishTime"])
    df["startTime"] = _utc(df["startTime"])
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = df.dropna(subset=["generation"]).drop_duplicates(["publishTime", "startTime"], keep="last")
    df["horizon_h"] = (df["startTime"] - df["publishTime"]).dt.total_seconds() / 3600.0
    return df[["publishTime", "startTime", "generation", "horizon_h"]].sort_values("publishTime").reset_index(drop=True)


def hourly_actuals(actuals_30m: pd.DataFrame) -> pd.DataFrame:
    """Average the two half-hours of each hour -> hourly actual MW."""
    if actuals_30m.empty:
        return pd.DataFrame({"startTime": pd.Series(dtype=NS_UTC), "actual": pd.Series(dtype=float)})
    h = actuals_30m.assign(startTime=actuals_30m["startTime"].dt.floor("h"))
    out = h.groupby("startTime", as_index=False)["generation"].mean().rename(columns={"generation": "actual"})
    out["startTime"] = out["startTime"].astype(NS_UTC)
    return out


def select_forecasts(fc: pd.DataFrame, targets: pd.Series, min_horizon_h: float = 0.0,
                     cutoffs: pd.Series | None = None) -> pd.DataFrame:
    """For every target hour pick the LATEST forecast published at/before its cutoff.

    cutoff = startTime - min_horizon_h (default) or an explicit per-target `cutoffs` series.
    Implemented with merge_asof (O(n log n)) so scanning all 48 horizons stays fast.
    """
    targets = pd.Series(pd.to_datetime(targets, utc=True)).astype(NS_UTC).reset_index(drop=True)
    if cutoffs is None:
        cut = targets - pd.Timedelta(hours=min_horizon_h)
    else:
        cut = pd.Series(pd.to_datetime(cutoffs, utc=True)).astype(NS_UTC).reset_index(drop=True)
    left = pd.DataFrame({"startTime": targets, "cutoff": cut}).sort_values("cutoff")
    right = fc[["publishTime", "startTime", "generation"]].rename(columns={"generation": "forecast"}).sort_values("publishTime")
    m = pd.merge_asof(left, right, left_on="cutoff", right_on="publishTime", by="startTime", direction="backward")
    m = m.dropna(subset=["publishTime"])
    m["horizon_h"] = (m["startTime"] - m["publishTime"]).dt.total_seconds() / 3600.0
    return m.sort_values("startTime").reset_index(drop=True)


def _bounds(start, end):
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    s = s.tz_localize("UTC") if s.tzinfo is None else s.tz_convert("UTC")
    e = e.tz_localize("UTC") if e.tzinfo is None else e.tz_convert("UTC")
    return s.floor("D"), e.floor("D") + pd.Timedelta(days=1)  # end date inclusive


def paired(fc: pd.DataFrame, act_hourly: pd.DataFrame, start, end, min_horizon_h: float = 0.0) -> pd.DataFrame:
    """Forecast/actual pairs for target hours in [start, end] (end date inclusive)."""
    s, e = _bounds(start, end)
    act = act_hourly[(act_hourly["startTime"] >= s) & (act_hourly["startTime"] < e)]
    sel = select_forecasts(fc, act["startTime"], min_horizon_h)
    out = sel.merge(act, on="startTime", how="inner")
    out["error"] = out["forecast"] - out["actual"]
    return out


def metrics(pairs: pd.DataFrame) -> dict:
    """Quantify forecast error. All MW unless stated."""
    n = int(len(pairs))
    if n == 0:
        return {"n": 0}
    err, act = pairs["error"].to_numpy(float), pairs["actual"].to_numpy(float)
    abs_err = np.abs(err)
    return {
        "n": n,
        "mae": float(abs_err.mean()),
        "rmse": float(np.sqrt((err ** 2).mean())),
        "bias": float(err.mean()),                              # + = over-forecast
        "wape_pct": float(abs_err.sum() / act.sum() * 100) if act.sum() > 0 else None,
        "p50_abs": float(np.percentile(abs_err, 50)),
        "p90_abs": float(np.percentile(abs_err, 90)),
        "p99_abs": float(np.percentile(abs_err, 99)),
        "max_abs": float(abs_err.max()),
        "err_p10": float(np.percentile(err, 10)),
        "err_p90": float(np.percentile(err, 90)),
        "mean_actual": float(act.mean()),
        "mean_forecast": float(pairs["forecast"].mean()),
    }


def error_by_horizon(fc, act_hourly, start, end, max_h: int = 48) -> list[dict]:
    """MAE/RMSE/bias if the buyer had to rely on a forecast made >= h hours ahead."""
    rows = []
    for h in range(0, max_h + 1):
        m = metrics(paired(fc, act_hourly, start, end, float(h)))
        if m["n"]:
            rows.append({"horizon_h": h, **{k: m[k] for k in ("n", "mae", "rmse", "bias", "p90_abs")}})
    return rows


def error_by_hour_of_day(pairs: pd.DataFrame) -> list[dict]:
    if pairs.empty:
        return []
    g = pairs.assign(hour=pairs["startTime"].dt.hour).groupby("hour")
    return [{"hour": int(h), "mae": float(d["error"].abs().mean()), "bias": float(d["error"].mean())} for h, d in g]


def _decision_cutoff(day: pd.Timestamp, cutoff_hour: int) -> pd.Timestamp:
    return day - pd.Timedelta(days=1) + pd.Timedelta(hours=cutoff_hour)


def _day_pairs(fc, act_hourly, day: pd.Timestamp, cutoff_hour: int) -> pd.DataFrame:
    hrs = pd.Series(pd.date_range(day, periods=24, freq="h", tz="UTC")).astype(NS_UTC)
    sel = select_forecasts(fc, hrs, cutoffs=pd.Series([_decision_cutoff(day, cutoff_hour)] * 24))
    out = sel.merge(act_hourly, on="startTime", how="left")
    out["error"] = out["forecast"] - out["actual"]
    return out


def day_ahead_view(fc: pd.DataFrame, act_hourly: pd.DataFrame, delivery_date, cutoff_hour: int) -> dict:
    """What the trader sees at decision time for delivery day D.

    Decision time = (D - 1 day) at `cutoff_hour`:00 UTC.  For each hour of D we show the latest
    forecast published at/before that time, plus an empirical P10-P90 band built from the error of
    the same decision rule on *earlier* days (no look-ahead). If fewer than 3 earlier days exist the
    band falls back to all other days and `band.basis` says so.
    """
    d = pd.Timestamp(delivery_date)
    d = (d.tz_localize("UTC") if d.tzinfo is None else d.tz_convert("UTC")).floor("D")
    out = _day_pairs(fc, act_hourly, d, cutoff_hour)

    all_days = sorted(act_hourly["startTime"].dt.floor("D").unique())
    pops = []
    for day in all_days:
        day = pd.Timestamp(day)
        if day == d:
            continue
        p = _day_pairs(fc, act_hourly, day, cutoff_hour).dropna(subset=["actual"])
        p["delivery_date"] = day
        pops.append(p)
    pop = pd.concat(pops) if pops else pd.DataFrame(columns=["error", "delivery_date"])
    earlier = pop[pop["delivery_date"] < d] if len(pop) else pop
    if len(earlier) and earlier["delivery_date"].nunique() >= 3:
        basis, src = "earlier_days", earlier
    else:
        basis, src = "all_other_days", pop

    if len(src):
        q10, q90 = float(np.percentile(src["error"], 10)), float(np.percentile(src["error"], 90))
    else:
        q10 = q90 = 0.0
    # actual = forecast - error  =>  actual lies in [forecast - q90, forecast - q10] (80% band)
    out["low"] = (out["forecast"] - q90).clip(lower=0)
    out["high"] = out["forecast"] - q10
    done = out.dropna(subset=["actual"])
    has = len(out) > 0
    return {
        "delivery_date": d.strftime("%Y-%m-%d"),
        "decision_time": _decision_cutoff(d, cutoff_hour).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "band": {"err_p10": q10, "err_p90": q90, "basis": basis,
                 "n_days": int(src["delivery_date"].nunique()) if len(src) else 0},
        "summary": {
            "mean_forecast": float(out["forecast"].mean()) if has else None,
            "peak_forecast": float(out["forecast"].max()) if has else None,
            "min_forecast": float(out["forecast"].min()) if has else None,
            "mean_low": float(out["low"].mean()) if has else None,
            "mean_high": float(out["high"].mean()) if has else None,
            "backtest": metrics(done) if len(done) else None,
        },
        "rows": records(out[["startTime", "publishTime", "horizon_h", "forecast", "low", "high", "actual", "error"]]),
    }


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe list of dicts (ISO timestamps, NaN -> None)."""
    out = df.copy()
    for c in out.columns:
        if str(out[c].dtype).startswith("datetime64"):
            out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out = out.astype(object).where(out.notna(), None)
    return out.to_dict("records")
