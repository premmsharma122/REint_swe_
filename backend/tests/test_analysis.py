"""Run with:  cd backend && pytest -q"""
import pandas as pd
import pytest

from app import analysis as A
from app.sample import make_sample


def _fc(rows):
    return A.clean_forecasts(pd.DataFrame(rows))


def test_latest_forecast_before_cutoff_is_chosen():
    fc = _fc([
        {"publishTime": "2026-01-01T00:00:00Z", "startTime": "2026-01-02T12:00:00Z", "generation": 100},
        {"publishTime": "2026-01-01T09:00:00Z", "startTime": "2026-01-02T12:00:00Z", "generation": 200},
        {"publishTime": "2026-01-01T15:00:00Z", "startTime": "2026-01-02T12:00:00Z", "generation": 300},
    ])
    t = pd.Series(pd.to_datetime(["2026-01-02T12:00:00Z"]))
    # needs >= 24h lead => cutoff 2026-01-01T12:00 -> the 09:00 forecast (not the later 15:00 one)
    assert A.select_forecasts(fc, t, 24)["forecast"].iloc[0] == 200
    assert A.select_forecasts(fc, t, 0)["forecast"].iloc[0] == 300
    assert A.select_forecasts(fc, t, 40).empty or A.select_forecasts(fc, t, 40)["forecast"].iloc[0] == 100


def test_no_forecast_available_is_dropped_not_filled():
    fc = _fc([{"publishTime": "2026-01-01T15:00:00Z", "startTime": "2026-01-02T12:00:00Z", "generation": 300}])
    t = pd.Series(pd.to_datetime(["2026-01-02T12:00:00Z"]))
    assert A.select_forecasts(fc, t, 24).empty


def test_hourly_actuals_average_two_half_hours():
    raw = pd.DataFrame({"startTime": ["2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z"],
                        "fuelType": ["WIND", "WIND"], "generation": [1000, 2000]})
    h = A.hourly_actuals(A.clean_actuals(raw))
    assert len(h) == 1 and h["actual"].iloc[0] == 1500


def test_clean_actuals_keeps_only_wind():
    raw = pd.DataFrame({"startTime": ["2026-01-01T00:00:00Z"] * 2, "fuelType": ["WIND", "CCGT"], "generation": [5, 99]})
    assert A.clean_actuals(raw)["generation"].tolist() == [5]


def test_metrics_values_and_sign_convention():
    p = pd.DataFrame({"forecast": [110.0, 90.0, 130.0], "actual": [100.0, 100.0, 100.0]})
    p["error"] = p["forecast"] - p["actual"]
    m = A.metrics(p)
    assert m["mae"] == pytest.approx((10 + 10 + 30) / 3)
    assert m["bias"] == pytest.approx(10.0)             # over-forecast on average
    assert m["rmse"] == pytest.approx(((100 + 100 + 900) / 3) ** 0.5)
    assert m["wape_pct"] == pytest.approx(50 / 300 * 100)


def test_metrics_empty():
    assert A.metrics(pd.DataFrame({"error": [], "actual": [], "forecast": []})) == {"n": 0}


@pytest.fixture(scope="module")
def data():
    a, f = make_sample()
    lo, hi = pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-02-01", tz="UTC")
    a30 = A.clean_actuals(a)
    act = A.hourly_actuals(a30[(a30["startTime"] >= lo) & (a30["startTime"] < hi)])   # mirror store.py scoping
    fc = A.clean_forecasts(f)
    fc = fc[(fc["startTime"] >= lo) & (fc["startTime"] < hi) & (fc["horizon_h"] >= 0) & (fc["horizon_h"] <= 48)]
    return fc, act


def test_error_grows_with_horizon_on_sample(data):
    fc, act = data
    rows = A.error_by_horizon(fc, act, "2026-01-01", "2026-01-31")
    assert rows[0]["mae"] < rows[-1]["mae"]


def test_paired_never_uses_forecast_published_after_cutoff(data):
    fc, act = data
    p = A.paired(fc, act, "2026-01-05", "2026-01-10", 12)
    assert ((p["startTime"] - p["publishTime"]).dt.total_seconds() / 3600 >= 12 - 1e-9).all()


def test_day_ahead_uses_cutoff_and_has_band(data):
    fc, act = data
    v = A.day_ahead_view(fc, act, "2026-01-15", 10)
    assert v["decision_time"] == "2026-01-14T10:00:00Z"
    assert len(v["rows"]) == 24
    assert all(r["publishTime"] <= v["decision_time"] for r in v["rows"])
    assert v["band"]["err_p10"] < v["band"]["err_p90"] and v["band"]["basis"] == "earlier_days"
    assert all(r["low"] <= r["forecast"] + 1e-6 or r["low"] == 0 for r in v["rows"])


def test_day_ahead_first_day_falls_back_and_flags(data):
    fc, act = data
    assert A.day_ahead_view(fc, act, "2026-01-01", 10)["band"]["basis"] == "all_other_days"
