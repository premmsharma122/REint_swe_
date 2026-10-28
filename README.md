# Wind Forecast Monitor

A web app that helps a UK energy buyer decide how much power to procure in the **day-ahead market**.
It shows (1) the latest wind-generation forecast available when a purchase decision has to be made, and
(2) how accurate those forecasts have been, in numbers, so the buyer can plan for the error.

| | |
|---|---|
| **Live app** | https://swech.vercel.app |
| **Demo video** (unlisted YouTube) | `<add link>` |
| **Stack** | React (Vite, Recharts) · Python (FastAPI, pandas) · Docker · Vercel |
| **Data** | Elexon BMRS only: `WINDFOR` (forecasts) and `FUELHH` (actuals, `fuelType = WIND`) |
| **Scope** | GB national wind generation · purchase decisions for **January 2026** |

> **AI usage disclosure:** this project was built with the help of an AI assistant (Claude by Anthropic) for
> scaffolding, code and documentation. The design decisions were reviewed, and the app was run and tested, by the author.

---

## 1. Problem context

The client is a UK energy utility. The team we serve buys power from the **day-ahead market**, and the purchase
decision must be made **one day before delivery**. Wind output is weather-dependent and unknown at that point, so the
buyer relies on forecasts to work out how much extra power (for example from thermal plants) is needed beyond wind.

The app answers two questions:

1. **What is the latest wind forecast available when I have to decide?**
2. **How accurate are these forecasts, quantitatively, so I can account for the error?**

## 2. How the requirements map to the app

| Requirement | What the app does | Where |
|---|---|---|
| Understand the latest forecast available at decision time | For a delivery day D, shows the latest forecast published before the D-1 cut-off (default 10:00 UTC, adjustable), hour by hour | *Day-ahead decision view* · `GET /api/day-ahead` |
| Evaluate forecast accuracy quantitatively | MAE, RMSE, bias, WAPE, P50/P90/P99 absolute error over any date range in January 2026 | KPI cards · `GET /api/metrics` |
| Compare forecast with actual generation | Hourly actual vs forecast line chart at a chosen lead time | *Forecast vs actual* · `GET /api/forecast-vs-actual` |
| Decide with the error in mind | Error-vs-lead-time curve, error by hour of day, and an 80% uncertainty band around the day-ahead forecast | *Error vs lead time*, *Error by hour of day*, band in the day-ahead view |

## 3. Data

| Dataset | Endpoint | Used fields |
|---|---|---|
| Actuals | `/datasets/FUELHH/stream` with `fuelType=WIND` | `startTime` (30-min), `generation` |
| Forecasts | `/datasets/WINDFOR/stream` | `startTime`, `publishTime`, `generation` |

- Base URL: `https://data.elexon.co.uk/bmrs/api/v1`. No API key is needed.
- `FUELHH` is queried by **settlement date**. The API returns HTTP 400 if settlement-date and publish-time parameters are mixed, so they are never combined.
- `WINDFOR` is queried by **publish time**, starting a few days before 1 January so that early-January targets still have forecasts made 24–48 hours ahead.
- Requests are chunked (default 7 days) with retry and back-off on HTTP 429/5xx.
- The January 2026 data is stored in `backend/data/*.json` and committed, so the deployed app needs no Elexon call at runtime (Vercel's filesystem is read-only). Refresh it with `python backend/scripts/fetch_data.py`.

## 4. Method and assumptions (please challenge these in review)

1. **Forecast selection.** WINDFOR holds many forecasts for each target hour, published at different times. For a lead time `h`,
   each target hour uses the **latest forecast published at least `h` hours before it** (`pandas.merge_asof`). This guarantees no
   future information leaks into the comparison.
2. **Day-ahead decision time.** Default cut-off is **10:00 UTC on D-1**, a stand-in for the day-ahead auction gate. It is configurable in the UI and in `config.py`.
   January is GMT (= UTC), so there is no daylight-saving ambiguity.
3. **Resolution.** WINDFOR is hourly, FUELHH is 30-minute. The two half-hours of each hour are averaged into an hourly actual.
4. **Error sign.** `error = forecast − actual`. Positive means wind was over-forecast, so the buyer would have under-procured (short position).
5. **Uncertainty band.** P10–P90 of past forecast errors under the same decision rule, using earlier days only (no look-ahead).
   With fewer than 3 earlier days it falls back to all other days, and the UI says so.
6. **Metrics.** MAE, RMSE, bias, WAPE (= sum of absolute errors ÷ sum of actuals; used instead of MAPE because wind can be near 0 MW),
   and P50/P90/P99 absolute error.
7. Forecasts with a horizon outside 0–48 hours are ignored. Target hours outside January 2026 are ignored.

## 5. API

| Endpoint | Parameters | Returns |
|---|---|---|
| `GET /api/health` | none | status, data source (`elexon` or `sample`), row counts, defaults |
| `GET /api/forecast-vs-actual` | `start`, `end` (YYYY-MM-DD), `horizon` (0–48 h) | hourly rows `{startTime, publishTime, forecast, actual, error}` and metrics |
| `GET /api/metrics` | `start`, `end`, `horizon` | summary metrics, `by_horizon` curve, `by_hour` profile |
| `GET /api/day-ahead` | `delivery_date`, `cutoff_hour` (0–23) | 24 hourly rows with forecast, low/high band and (if known) actual, plus band details and summary |

Dates must fall inside January 2026. Interactive docs are available at `/docs` when the backend runs locally.

## 6. Repository layout

```
api/
  index.py             Vercel serverless entry point (exposes the FastAPI app)
backend/
  app/
    config.py          settings: scope dates, cut-off hour, env overrides
    elexon.py          Elexon API client (chunked requests, retry/back-off)
    store.py           loads data once: sample | data/*.json cache | live fetch
    analysis.py        pure pandas logic: cleaning, forecast selection, metrics, day-ahead view
    sample.py          synthetic data generator (offline dev and tests only)
    main.py            FastAPI routes; serves the React build inside Docker
  scripts/
    fetch_data.py      downloads January 2026 data into backend/data/
  tests/
    test_analysis.py   unit tests for the analysis logic
  data/                cached Elexon JSON (committed)
  requirements.txt     runtime dependencies
  requirements-dev.txt test dependencies
frontend/
  src/App.jsx          the whole UI: controls, KPI cards, charts
  src/api.js           small fetch wrapper
  src/styles.css       styling (light and dark)
  vite.config.js       dev server, proxies /api to :8000
Dockerfile             multi-stage: builds React, then Python image serving API and UI
docker-compose.yml     one-command local run
vercel.json            Vercel build + routing: /api/* -> api/index.py
requirements.txt       Python dependencies used by Vercel
```

## 7. Run locally

Prerequisites: Python 3.10+ and Node 18+. A virtual environment is recommended.

**Backend**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/fetch_data.py                  # only if backend/data/*.json is missing
python -m uvicorn app.main:app --reload       # http://localhost:8000  (API docs at /docs)
```
To run offline with synthetic data, start with `USE_SAMPLE_DATA=1 python -m uvicorn app.main:app --reload`.
The UI shows a "SYNTHETIC SAMPLE DATA" badge in that mode.

**Frontend** (new terminal)
```bash
cd frontend
npm install
npm run dev                                   # http://localhost:5173
```

**Docker** (single container with UI and API)
```bash
docker compose up --build                     # http://localhost:8000
```

**Tests**
```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

## 8. Deployment (Vercel)

The live app runs on Vercel as one project: the React build is served as static files and the FastAPI app runs as a Python serverless function.

1. Push the repository to GitHub (with `backend/data/*.json` committed).
2. On vercel.com choose **Add New → Project** and import the repository.
3. Set **Application Preset: Other** and **Root Directory: `./`**. Do not use the per-folder "Import single project" buttons.
4. Deploy. Build settings come from `vercel.json`, which builds `frontend/`, serves `frontend/dist`, routes `/api/*` to `api/index.py` and bundles `backend/**`.
5. Verify `https://swech.vercel.app/api/health` returns `status: ok` and `source: elexon`.

Every push to the main branch redeploys automatically, and pull requests get a preview URL.

## 9. Key development practices

- **Pure analysis layer.** All forecasting maths lives in `analysis.py` with no I/O, so it is unit-tested without a server or network.
- **No look-ahead.** Forecast selection and the uncertainty band only use information available at the decision time.
- **Reproducible data.** Real data is snapshotted to JSON and committed, so deployments are deterministic and do not depend on Elexon being up.
- **Defensive API client.** Chunked requests, timeouts and retry with back-off for rate limits and transient errors.
- **Validated inputs.** Dates are checked against the January 2026 scope and horizons against 0–48 hours, with clear 400 errors.
- **Tests** cover forecast selection (latest before cut-off, none available), metric values and sign convention, hourly aggregation, the WIND-only filter, and the day-ahead cut-off and band logic.

## 10. Limitations and next steps

- Wind only, with no demand or price data (per the brief), so the app shows wind uncertainty, not the total volume to procure.
- The uncertainty band is an empirical quantile band, not conditional on wind level (errors are larger at high output).
- The cut-off hour is an assumption standing in for the real auction gate time.
- Next: per-wind-regime error bands, CI (pytest + build), an end-to-end smoke test, and caching headers on the API.
