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
MAX_ENRICH_PER_RUN = int(os.environ.get("RECALL_RADAR_MAX_ENRICH", "20"))
# Give up on a recall after this many failed enrichment attempts.
MAX_ENRICH_ATTEMPTS = int(os.environ.get("RECALL_RADAR_MAX_ENRICH_ATTEMPTS", "3"))
ENRICH_ENABLED = bool(TAVILY_API_KEY)

# --- MCP server ---
TRANSPORT = os.environ.get("RECALL_RADAR_TRANSPORT", "stdio")
HOST = os.environ.get("RECALL_RADAR_HOST", "0.0.0.0")
PORT = int(os.environ.get("RECALL_RADAR_PORT", "8000"))
