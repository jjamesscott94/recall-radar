# Recall Radar 🥫🚨

**Nightly-updated intelligence on active US food recalls — exposed to AI agents as an MCP server.**

Every night, Recall Radar pulls the authoritative list of active food recalls from
[openFDA](https://open.fda.gov) (which covers both FDA *and* USDA/FSIS meat & poultry
recalls), then uses **Tavily Pro Research** to build a *dense, decision-ready profile* of
each recall: the parent company, its brand portfolio, the specific contaminant or cause,
affected states, prior recall history, and — critically — **red flags about weak
food-safety reporting and oversight controls**.

The result is a single committed `data/recalls.json` that any AI agent can query through
the bundled MCP server to answer: *"what foods, brands, and companies should I avoid right
now?"*

---

## How it works

```
openFDA food/enforcement (status:Ongoing)   ← authoritative, free, keyless
        │
        ▼
normalize → canonical recall records
        │
        ▼
Tavily Pro Research (structured output_schema)   ← dense enrichment per recall
        │
        ▼
data/recalls.json   ← committed nightly by GitHub Actions
        │
        ▼
FastMCP server (stdio or streamable-http)   ← agents query it
```

## Quick start

**Requirements:** Python 3.10+ and [`uv`](https://docs.astral.sh/uv/) (recommended).
`uv` handles the virtualenv and dependencies for you, so there's no manual
install step.

### 1. Run the MCP server locally (stdio)

```bash
git clone https://github.com/jjamesscott94/recall-radar.git
cd recall-radar
uv run recall-radar-server          # stdio transport by default
```

Point any MCP client at it. The robust form uses `uv run --directory` with an
absolute path, so it works regardless of the client's working directory:

```json
{
  "mcpServers": {
    "recall-radar": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/recall-radar", "recall-radar-server"]
    }
  }
}
```

If you prefer `pip` over `uv`:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip   # required: stock pip can't do editable installs
.venv/bin/pip install -e .
.venv/bin/recall-radar-server
```

### 2. Run the pipeline yourself

```bash
# OpenFDA-only (no key needed — still produces a valid dataset):
uv run recall-radar

# With Tavily enrichment:
export TAVILY_API_KEY=tvly-...
uv run recall-radar
```

### 3. Host it as a network endpoint (optional)

```bash
export RECALL_RADAR_TRANSPORT=streamable-http
export RECALL_RADAR_PORT=8000
uv run recall-radar-server
# → http://localhost:8000/mcp  (streamable HTTP MCP endpoint)
```

Or deploy the included `Dockerfile` to GCP Cloud Run and point a Cloud Scheduler job
at the pipeline to keep the dataset fresh.

## MCP tools

| Tool | What it does |
|---|---|
| `search_recalls` | Keyword search across brand, company, product, contaminant, state |
| `get_recall` | Full record (incl. enrichment) for one recall id |
| `list_active_recalls` | All active recalls, optional Class I/II/III filter |
| `get_company_profile` | Aggregated profile: brands, recall history, red flags |
| `brands_to_avoid` | Deduplicated companies with active recalls, ranked by severity |
| `recall_timeline` | Recalls ordered by date, optional company filter + lookback |
| `dataset_stats` | Freshness, counts, classification breakdown, top firms |

## Nightly automation

The pipeline runs **every other day** (odd days of the month, 08:00 UTC) to keep
Tavily spend bounded. The schedule is owned by **Google Cloud Scheduler**, which
fires a small Cloud Function that triggers the GitHub Actions workflow via
`workflow_dispatch` — a single source of truth, with the GitHub token held in
Secret Manager (never in the repo).

```
Cloud Scheduler (0 8 */2 * *)  →  Cloud Function (OIDC-auth)  →  GitHub workflow_dispatch
                                                                      │
                                                                      ▼
                                              openFDA pull → Tavily enrich → commit data/recalls.json
```

To enable enrichment, add your Tavily key as a repo secret:

```
Settings → Secrets and variables → Actions → New repository secret
Name:  TAVILY_API_KEY
Value: tvly-...
```

Without the secret, the workflow still runs and updates the openFDA data — it just skips
the Tavily enrichment layer. The `gcp/trigger-function/` directory contains the Cloud
Function source for anyone who wants to reproduce the scheduler wiring.

## Web dashboard

A zero-dependency dashboard (`index.html`) renders the dataset for humans — served
via GitHub Pages. It shows the active-recall counts by severity, a searchable/filterable
list, and the enriched "brands to avoid" profiles with red flags.

## Data sources & coverage

- **openFDA `food/enforcement`** — the authoritative US recall registry. Covers FDA food
  *and* USDA/FSIS meat & poultry. Free, no API key, structured fields (recalling firm,
  product, reason, classification, distribution, UPC/lot codes).
- **Tavily Pro Research** — enrichment layer producing the company/brand/history/red-flag
  profile, with citations to FDA, USDA/FSIS, CDC, and company sources.

## Configuration

All via environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `TAVILY_API_KEY` | *(empty)* | Enables enrichment when set |
| `TAVILY_MODEL` | `mini` | Tavily research model (`mini` 4–110 credits/req, `pro` 15–250) |
| `RECALL_RADAR_DATA_DIR` | `data` | Where `recalls.json` lives |
| `RECALL_RADAR_MAX_ENRICH` | `10` | Max recalls enriched per run (spend guard) |
| `RECALL_RADAR_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `RECALL_RADAR_HOST` / `RECALL_RADAR_PORT` | `0.0.0.0` / `8000` | HTTP bind |
| `RECALL_RADAR_DATA_URL` | *(empty)* | URL to self-refresh the dataset from (hosted) |
| `RECALL_RADAR_RATE_LIMIT_REQUESTS` | `60` | Per-IP requests per window (hosted) |
| `RECALL_RADAR_RATE_LIMIT_WINDOW` | `60` | Rate-limit window in seconds (hosted) |

## Security & cost posture

See [SECURITY.md](SECURITY.md) for the full picture. The short version:

- **The Tavily key is never committed** — it lives only in GitHub Actions secrets,
  Secret Manager, or your local (gitignored) `.env`.
- **The expensive path is not public** — Tavily enrichment runs only inside the
  nightly workflow, which is triggered exclusively by a locked-down Cloud Function.
- **The public endpoint is read-only and rate-limited** — it serves the committed
  `recalls.json` from memory (no Tavily, no writes) and enforces a per-IP
  sliding-window cap, so a flood gets `429` before it costs anything meaningful.
- **Spend is bounded** — `mini` model by default, `RECALL_RADAR_MAX_ENRICH=10`
  per run, every-other-day schedule.

## License

MIT — see [LICENSE](LICENSE).
