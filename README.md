# Wind Forecast Monitor

Web app that helps a UK energy buyer decide how much power to procure in the **day-ahead market**,
by showing (1) the latest wind-generation forecast available at decision time and (2) how accurate
those forecasts have historically been. Scope: GB national wind, **January 2026**, Elexon BMRS data only.

**Live app:** `<add your Heroku / Render / Vercel URL here>`
**Demo video:** `<add unlisted YouTube link>`

> **AI usage disclosure:** this project was built with the help of an AI assistant (Claude by Anthropic) for scaffolding, code and documentation. All design decisions and the final code were reviewed by the author.

## What it does

| Question the trader has | Where in the UI | API |
|---|---|---|
| How does forecast compare to what really happened? | *Forecast vs actual* chart | `GET /api/forecast-vs-actual` |
| How wrong is the forecast, in numbers? | KPI cards (MAE, RMSE, bias, WAPE, P90) | `GET /api/metrics` |
| How much worse does it get the earlier I must decide? | *Error vs lead time* chart | `GET /api/metrics` (`by_horizon`) |
| What do I see on D-1 for tomorrow, and how much should I hedge? | *Day-ahead decision view* | `GET /api/day-ahead` |

### Key modelling decisions (assumptions to challenge in review)
1. **Forecast selection.** WINDFOR holds many forecasts per target hour (published at different times).
   For a lead time `h`, each target hour uses the **latest forecast published at least `h` hours before it**
   (`merge_asof`, so no future information leaks in).
2. **Day-ahead decision time.** Default = 10:00 UTC on D-1 (configurable) as a stand-in for the auction gate.
   January is GMT = UTC, so there is no DST ambiguity.
3. **Resolution.** WINDFOR is hourly, FUELHH is 30-min → actuals are averaged to hourly means.
4. **Error sign.** `error = forecast − actual`. Positive = over-forecast = buyer under-procures thermal (short).
5. **Uncertainty band** in the day-ahead view = P10–P90 of past errors under the same decision rule
   (earlier days only; falls back to other days, flagged in the UI, when < 3 days of history).
6. **Metrics.** MAE, RMSE, bias, WAPE (used instead of MAPE because wind can be near 0 MW), P50/P90/P99 absolute error.
7. Forecasts with horizon outside 0–48 h are ignored.

## Repo layout
```
backend/
  app/config.py      settings (scope dates, cut-off hour, env overrides)
  app/elexon.py      Elexon API client (chunked requests, retry/back-off)
  app/store.py       loads data once: sample | data/*.json cache | live fetch
  app/analysis.py    PURE pandas logic: cleaning, forecast selection, metrics, day-ahead view
  app/sample.py      synthetic data generator (offline dev / CI only)
  app/main.py        FastAPI routes; serves the React build in Docker
  scripts/fetch_data.py   downloads Jan-2026 data into backend/data/
  tests/test_analysis.py  unit tests
  data/              cached Elexon JSON (commit after running fetch_data.py)
frontend/            Vite + React + Recharts (src/App.jsx is the whole UI)
Dockerfile           multi-stage: build React -> Python image serving API + UI
docker-compose.yml   local run;  heroku.yml  Heroku container deploy
```

## Run it

**1. Get the real data once** (needs internet; writes `backend/data/*.json`):
```bash
cd backend && pip install -r requirements.txt && python scripts/fetch_data.py
```
(If the cache is missing the app fetches live on first request; with `USE_SAMPLE_DATA=1` it uses synthetic data.)

**2. Docker (single container, UI + API):**
```bash
docker compose up --build        # http://localhost:8000
```

**3. Local dev (hot reload):**
```bash
cd backend && uvicorn app.main:app --reload            # :8000
cd frontend && npm install && npm run dev               # :5173 (proxies /api)
```

**Tests:** `cd backend && pip install -r requirements-dev.txt && pytest -q`

## Deploy (Heroku, container stack)
```bash
heroku create <name> --stack container
git push heroku main
```
Commit `backend/data/*.json` first so the dyno does not need to call Elexon at boot.

## Limitations / next steps
- Wind only, no demand/price data (per brief) → we show the *wind* uncertainty, not the full procurement volume.
- Error band is a simple empirical quantile band, not conditional on wind level (errors are larger at high output).
- Would add: caching headers, CI (pytest + build), Playwright smoke test, per-wind-regime error bands.
