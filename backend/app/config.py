"""Central configuration. Everything is overridable through environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))

ELEXON_BASE_URL = os.getenv("ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1")
CHUNK_DAYS = int(os.getenv("ELEXON_CHUNK_DAYS", "7"))  # keep each API call small
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "60"))

# Scope of the challenge: purchase decisions made in January 2026 only.
# UK is on GMT (== UTC) in January, so there is no daylight-saving ambiguity.
SCOPE_START = "2026-01-01"
SCOPE_END = "2026-01-31"
# Forecasts for 1 Jan can be published up to ~2 days earlier -> fetch a lead-in window.
FORECAST_LEAD_IN_DAYS = 4

MAX_HORIZON_H = 48
# Day-ahead auction gate closes around midday; default decision time = 10:00 UTC on D-1.
DEFAULT_CUTOFF_HOUR = 10

# If set to 1 the app uses a synthetic dataset (useful offline / for CI).
USE_SAMPLE_DATA = os.getenv("USE_SAMPLE_DATA", "0") == "1"
