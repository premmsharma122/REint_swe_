"""Synthetic wind data in the exact shape Elexon returns. ONLY for offline dev/tests/CI.
Forecast error grows with horizon (sigma = 250 + 70*h MW) and has a small positive bias."""
import numpy as np
import pandas as pd


def make_sample(start="2026-01-01", end="2026-01-31", lead_in_days=4, seed=7):
    rng = np.random.default_rng(seed)
    s = pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=lead_in_days)
    e = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    hours = pd.date_range(s, e, freq="h", inclusive="left")
    # smooth AR(1) "weather" signal -> MW between ~500 and ~17000
    x, level = np.zeros(len(hours)), 0.0
    for i in range(len(hours)):
        level = 0.985 * level + rng.normal(0, 0.12)
        x[i] = level
    true = np.clip(8000 + 5500 * x / (x.std() + 1e-9), 300, 17500)

    act = []
    for t, v in zip(hours, true):
        for k in (0, 30):
            act.append({"dataset": "FUELHH", "startTime": (t + pd.Timedelta(minutes=k)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "fuelType": "WIND", "generation": int(max(0, v + rng.normal(0, 60)))})
    fc = []
    idx = {t: v for t, v in zip(hours, true)}
    for pub in pd.date_range(s, e - pd.Timedelta(hours=1), freq="3h"):
        for h in range(0, 49):
            t = pub + pd.Timedelta(hours=h)
            if t in idx:
                g = max(0, idx[t] + 120 + rng.normal(0, 250 + 70 * h))
                fc.append({"dataset": "WINDFOR", "publishTime": pub.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "startTime": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "generation": int(g)})
    return pd.DataFrame(act), pd.DataFrame(fc)
