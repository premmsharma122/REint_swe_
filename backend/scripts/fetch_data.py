"""Download January 2026 wind actuals + forecasts from Elexon into backend/data/*.json.
Run once (needs internet), then commit the files so the deployed app starts instantly.
    python scripts/fetch_data.py
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import store  # noqa: E402

logging.basicConfig(level=logging.INFO)
store.refresh_cache()
print("Saved:", store.ACT_FILE, store.FC_FILE)
