"""Recall Radar MCP server.

Exposes the nightly recall dataset to AI agents via the Model Context Protocol.
Supports two transports (env `RECALL_RADAR_TRANSPORT`):
  - `stdio` (default): run locally, connect any MCP client via stdio.
  - `streamable-http`: host a network endpoint (e.g. on GCP Cloud Run).

The dataset is loaded from `data/recalls.json` into memory at startup.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import httpx
from fastmcp import FastMCP

from . import config
from .store import load

log = logging.getLogger("recall-radar.server")

mcp = FastMCP(
    "recall-radar",
    instructions=(
        "Recall Radar provides nightly-updated intelligence on active US food "
        "recalls. Use it to identify foods, brands, and companies to avoid due "
        "to recalls and weak food-safety reporting controls. Data is sourced "
        "from openFDA (authoritative recall records) and enriched with Tavily "
        "Pro Research (company profiles, brand portfolios, recall history, and "
        "reporting-controls red flags)."
    ),
)

# Load once at import/startup.
_dataset = load()
_recalls = _dataset.get("recalls", [])


def _reload() -> None:
    """Re-read the dataset from disk (useful if the file is refreshed)."""
    global _dataset, _recalls
    _dataset = load()
    _recalls = _dataset.get("recalls", [])


def _refresh_from_url() -> None:
    """Fetch the latest dataset from DATA_URL and swap it in (best-effort)."""
    global _dataset, _recalls
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(config.DATA_URL)
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict) and "recalls" in data:
            _dataset = data
            _recalls = data.get("recalls", [])
            log.info("refreshed dataset from URL: %d recalls (generated %s)",
                     len(_recalls), data.get("generated_at"))
        else:
            log.warning("DATA_URL returned unexpected shape; keeping current dataset")
    except Exception as exc:  # noqa: BLE001
        log.warning("refresh from DATA_URL failed: %s", exc)


def _start_refresh_loop() -> None:
    """Background thread that periodically re-fetches DATA_URL (if configured)."""
    if not config.DATA_URL:
        return

    def loop():
        while True:
            threading.Event().wait(config.DATA_REFRESH_SECONDS)
            _refresh_from_url()

    t = threading.Thread(target=loop, daemon=True, name="recall-radar-refresh")
    t.start()
    log.info("started refresh loop: %s every %ds", config.DATA_URL, config.DATA_REFRESH_SECONDS)


def _public(rec: dict) -> dict:
    """Strip internal bookkeeping fields before returning to agents."""
    return {k: v for k, v in rec.items() if not k.startswith("_")}


def _match(rec: dict, query: str) -> bool:
    """Case-insensitive substring match across the searchable text of a record."""
    q = query.lower()
    haystack = " ".join(
        str(rec.get(k) or "")
        for k in (
            "recalling_firm",
            "product_description",
            "reason_for_recall",
            "brands",
            "distribution_pattern",
            "code_info",
            "classification",
            "state",
            "city",
        )
    ).lower()
    # Also search enrichment text.
    enr = rec.get("enrichment") or {}
    if isinstance(enr, dict):
        haystack += " " + json.dumps(enr).lower()
    return q in haystack


# --- Tools -----------------------------------------------------------------


@mcp.tool
def search_recalls(query: str, limit: int = 20) -> str:
    """Search active recalls by keyword (brand, company, product, contaminant, state).

    Args:
        query: Free-text search (e.g. "listeria", "Boar's Head", "peanut", "California").
        limit: Max results to return (default 20, max 100).
    """
    limit = max(1, min(limit, 100))
    hits = [r for r in _recalls if _match(r, query)]
    # Most severe first, then most recent.
    hits.sort(key=lambda r: (r.get("severity_rank", 4), r.get("report_date") or ""), reverse=False)
    return json.dumps([_public(r) for r in hits[:limit]], ensure_ascii=False, indent=2)


@mcp.tool
def get_recall(recall_id: str) -> str:
    """Get the full record (including enrichment) for a single recall by id.

    Args:
        recall_id: The recall id (openFDA event_id, e.g. "75272").
    """
    for r in _recalls:
        if r.get("id") == recall_id:
            return json.dumps(_public(r), ensure_ascii=False, indent=2)
    return json.dumps({"error": f"no recall with id {recall_id!r}"})


@mcp.tool
def list_active_recalls(classification: str | None = None, limit: int = 50) -> str:
    """List currently-active recalls, optionally filtered by FDA classification.

    Args:
        classification: Optional filter — "Class I", "Class II", or "Class III".
        limit: Max results (default 50, max 200).
    """
    limit = max(1, min(limit, 200))
    recs = _recalls
    if classification:
        recs = [r for r in recs if (r.get("classification") or "").lower() == classification.lower()]
    recs = sorted(recs, key=lambda r: (r.get("severity_rank", 4), r.get("report_date") or ""))
    return json.dumps([_public(r) for r in recs[:limit]], ensure_ascii=False, indent=2)


@mcp.tool
def get_company_profile(company: str) -> str:
    """Get the enriched profile for a company: brands, recall history, red flags.

    Args:
        company: Company or brand name (e.g. "Boar's Head", "Nestle").
    """
    q = company.lower()
    matches = [r for r in _recalls if q in (r.get("recalling_firm") or "").lower()
               or (isinstance(r.get("enrichment"), dict)
                   and q in json.dumps(r.get("enrichment")).lower())]
    if not matches:
        return json.dumps({"error": f"no recalls found for company {company!r}"})

    # Aggregate across all matching recalls.
    brands: set[str] = set()
    red_flags: set[str] = set()
    history: list[dict] = []
    for r in matches:
        enr = r.get("enrichment") or {}
        if isinstance(enr, dict):
            brands.update(enr.get("brands") or [])
            red_flags.update(enr.get("reporting_controls_red_flags") or [])
            history.extend(enr.get("recall_history") or [])

    profile = {
        "company": company,
        "active_recall_count": len(matches),
        "brands": sorted(brands),
        "reporting_controls_red_flags": sorted(red_flags),
        "recall_history": history,
        "recall_ids": [r.get("id") for r in matches],
    }
    return json.dumps(profile, ensure_ascii=False, indent=2)


@mcp.tool
def brands_to_avoid() -> str:
    """Return a deduplicated list of brands/companies with active recalls, ranked by severity."""
    from collections import defaultdict

    by_firm: dict[str, dict] = defaultdict(lambda: {"count": 0, "worst": 4, "reasons": set()})
    for r in _recalls:
        firm = r.get("recalling_firm") or "unknown"
        entry = by_firm[firm]
        entry["count"] += 1
        entry["worst"] = min(entry["worst"], r.get("severity_rank", 4))
        entry["reasons"].add(r.get("reason_for_recall") or "")

    rows = []
    for firm, e in by_firm.items():
        rows.append({
            "company": firm,
            "active_recalls": e["count"],
            "worst_classification": {1: "Class I", 2: "Class II", 3: "Class III", 4: "Unknown"}[e["worst"]],
            "reasons": sorted(e["reasons"]),
        })
    rows.sort(key=lambda x: (x["worst_classification"] != "Class I", -x["active_recalls"]))
    return json.dumps(rows, ensure_ascii=False, indent=2)


@mcp.tool
def recall_timeline(company: str | None = None, days: int = 30) -> str:
    """Return recalls ordered by date, optionally filtered to a company, within N days.

    Args:
        company: Optional company/brand filter.
        days: Lookback window in days (default 30).
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recs = _recalls
    if company:
        q = company.lower()
        recs = [r for r in recs if q in (r.get("recalling_firm") or "").lower()]

    dated = []
    for r in recs:
        d = r.get("report_date") or r.get("recall_initiation_date")
        if d:
            try:
                dt = datetime.fromisoformat(d)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff:
                    dated.append((dt, r))
            except ValueError:
                continue

    dated.sort(key=lambda x: x[0], reverse=True)
    out = [{"date": dt.date().isoformat(), **_public(r)} for dt, r in dated]
    return json.dumps(out, ensure_ascii=False, indent=2)


@mcp.tool
def dataset_stats() -> str:
    """Return summary statistics about the current dataset (counts, freshness, coverage)."""
    from collections import Counter

    cls = Counter(r.get("classification") for r in _recalls)
    enriched = sum(1 for r in _recalls if r.get("_enriched"))
    stats = {
        "generated_at": _dataset.get("generated_at"),
        "total_active_recalls": len(_recalls),
        "enriched": enriched,
        "unenriched": len(_recalls) - enriched,
        "by_classification": dict(cls),
        "top_recalling_firms": [
            {"firm": f, "count": c}
            for f, c in Counter(r.get("recalling_firm") for r in _recalls).most_common(10)
        ],
    }
    return json.dumps(stats, ensure_ascii=False, indent=2)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info("loaded %d recalls (generated %s)", len(_recalls), _dataset.get("generated_at"))
    _start_refresh_loop()

    if config.TRANSPORT == "streamable-http":
        log.info("serving streamable-http on %s:%d", config.HOST, config.PORT)
        mcp.run(transport="streamable-http", host=config.HOST, port=config.PORT)
    else:
        log.info("serving stdio")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
