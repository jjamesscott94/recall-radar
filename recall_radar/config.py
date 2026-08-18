"""Configuration, driven entirely by environment variables with sane defaults."""

import os
from pathlib import Path

# --- openFDA ---
OPENFDA_BASE_URL = os.environ.get("OPENFDA_BASE_URL", "https://api.fda.gov")
OPENFDA_ENDPOINT = "/food/enforcement.json"

# --- Tavily Pro Research ---
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "").strip()
TAVILY_BASE_URL = os.environ.get("TAVILY_BASE_URL", "https://api.tavily.com")
TAVILY_MODEL = os.environ.get("TAVILY_MODEL", "pro")

# --- Data ---
DATA_DIR = Path(os.environ.get("RECALL_RADAR_DATA_DIR", "data"))
JSON_PATH = Path(os.environ.get("RECALL_RADAR_JSON_PATH", DATA_DIR / "recalls.json"))

# --- Pipeline ---
# Cap on how many recalls get enriched per run, to bound Tavily spend.
# Conservative default (10) — each Tavily Pro research task costs credits.
MAX_ENRICH_PER_RUN = int(os.environ.get("RECALL_RADAR_MAX_ENRICH", "10"))
# Give up on a recall after this many failed enrichment attempts.
MAX_ENRICH_ATTEMPTS = int(os.environ.get("RECALL_RADAR_MAX_ENRICH_ATTEMPTS", "3"))
# Pause between enrichment requests (seconds) to stay under Tavily's 20 RPM
# research rate limit. 5s = 12 RPM, comfortably safe.
ENRICH_INTERVAL_SECONDS = float(os.environ.get("RECALL_RADAR_ENRICH_INTERVAL", "5"))
ENRICH_ENABLED = bool(TAVILY_API_KEY)

# --- MCP server ---
TRANSPORT = os.environ.get("RECALL_RADAR_TRANSPORT", "stdio")
HOST = os.environ.get("RECALL_RADAR_HOST", "0.0.0.0")
# Prefer RECALL_RADAR_PORT, then the standard PORT (Cloud Run sets PORT=8080),
# then 8000 as a local default.
PORT = int(os.environ.get("RECALL_RADAR_PORT", os.environ.get("PORT", "8000")))
# Optional: URL to fetch the latest recalls.json from (e.g. the GitHub raw URL).
# When set, the server refreshes its in-memory dataset from this URL on a
# schedule, so a hosted instance stays fresh without redeploying.
DATA_URL = os.environ.get("RECALL_RADAR_DATA_URL", "").strip()
# How often (seconds) to re-fetch DATA_URL. Default 6h.
DATA_REFRESH_SECONDS = int(os.environ.get("RECALL_RADAR_DATA_REFRESH_SECONDS", "21600"))
