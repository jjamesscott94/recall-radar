"""Nightly pipeline: openFDA pull -> normalize -> Tavily enrichment -> save.

Idempotent and incremental:
  - Existing records are preserved (including their enrichment) and only
    updated when openFDA reports a change.
  - New records are normalized and queued for enrichment.
  - Enrichment is bounded by MAX_ENRICH_PER_RUN and per-record attempt caps.
  - Runs WITHOUT a Tavily key: pulls + normalizes openFDA only, skips
    enrichment, and still produces a valid recalls.json.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone

from . import config
from .models import (
    ENRICHMENT_SCHEMA,
    build_enrichment_prompt,
    normalize_record,
)
from .openfda import fetch_active_recalls
from .store import build_dataset, load, save
from .tavily_research import run_research

log = logging.getLogger("recall-radar")


def _merge(existing: dict, incoming: dict) -> dict:
    """Merge an incoming normalized record over an existing one, preserving
    enrichment and bookkeeping unless the underlying data changed."""
    if not existing:
        return incoming

    # Preserve enrichment + bookkeeping.
    incoming["enrichment"] = existing.get("enrichment")
    incoming["_enriched"] = existing.get("_enriched", False)
    incoming["_enrich_attempts"] = existing.get("_enrich_attempts", 0)
    incoming["_first_seen"] = existing.get("_first_seen", incoming["_first_seen"])

    # If the substantive fields changed, bump last_updated and re-queue.
    changed = any(
        existing.get(k) != incoming.get(k)
        for k in (
            "product_description",
            "reason_for_recall",
            "classification",
            "status",
            "distribution_pattern",
            "code_info",
        )
    )
    if changed:
        incoming["_last_updated"] = datetime.now(timezone.utc).isoformat()
        incoming["_enriched"] = False  # re-enrich on changed data
    else:
        incoming["_last_updated"] = existing.get("_last_updated", incoming["_last_updated"])

    return incoming


def _enrich(rec: dict) -> None:
    """Enrich a single record via Tavily Pro Research. Never raises."""
    if rec.get("_enriched"):
        return
    if rec.get("_enrich_attempts", 0) >= config.MAX_ENRICH_ATTEMPTS:
        return

    rec["_enrich_attempts"] = rec.get("_enrich_attempts", 0) + 1
    try:
        content, sources = run_research(
            build_enrichment_prompt(rec),
            output_schema=ENRICHMENT_SCHEMA,
            include_domains=["fda.gov", "fsis.usda.gov", "cdc.gov"],
        )
        rec["enrichment"] = content
        rec["sources"] = sources
        rec["_enriched"] = True
        rec["_enriched_at"] = datetime.now(timezone.utc).isoformat()
        log.info("enriched %s (%s)", rec.get("id"), rec.get("recalling_firm"))
    except Exception as exc:  # noqa: BLE001 — enrichment is best-effort
        log.warning("enrichment failed for %s: %s", rec.get("id"), exc)


def run() -> dict:
    """Run the full pipeline and return the resulting dataset."""
    log.info("pulling active recalls from openFDA...")
    raw = fetch_active_recalls()
    log.info("openFDA returned %d active records", len(raw))

    existing = load()
    existing_by_id = {r.get("id"): r for r in existing.get("recalls", [])}

    merged: list[dict] = []
    new_ids: list[str] = []
    for r in raw:
        rec = normalize_record(r)
        merged_rec = _merge(existing_by_id.get(rec["id"]), rec)
        if rec["id"] not in existing_by_id:
            new_ids.append(rec["id"])
        merged.append(merged_rec)

    # Enrichment: new records first, then any re-queued (changed) records.
    if config.ENRICH_ENABLED:
        # Exclude records that are already enriched or have exhausted their
        # attempt budget — otherwise the per-run budget is wasted on no-ops.
        to_enrich = [
            r
            for r in merged
            if not r.get("_enriched")
            and r.get("_enrich_attempts", 0) < config.MAX_ENRICH_ATTEMPTS
        ]
        # New records take priority.
        to_enrich.sort(key=lambda r: 0 if r["id"] in new_ids else 1)
        budget = config.MAX_ENRICH_PER_RUN
        for rec in to_enrich:
            if budget <= 0:
                log.info("enrichment budget exhausted; %d remain unenriched", len(to_enrich))
                break
            # Decrement on EVERY attempt (success or failure) so a burst of
            # failures can never exceed the per-run cap and trip rate limits.
            budget -= 1
            _enrich(rec)
            # Small pause keeps us well under Tavily's 20 RPM research limit.
            time.sleep(config.ENRICH_INTERVAL_SECONDS)
    else:
        log.info("no TAVILY_API_KEY set — skipping enrichment (openFDA-only run)")

    dataset = build_dataset(merged)
    save(dataset)
    log.info("saved %d recalls to %s", len(merged), config.JSON_PATH)
    return dataset


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        log.exception("pipeline failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
