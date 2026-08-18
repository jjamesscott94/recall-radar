"""Data models and normalization for recall records.

The canonical record shape is a superset of the openFDA enforcement record,
plus an optional `enrichment` object produced by Tavily Pro Research.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# openFDA fields we keep verbatim (stable, useful for agents).
KEEP_FIELDS = [
    "event_id",
    "recall_number",
    "recalling_firm",
    "product_description",
    "product_quantity",
    "reason_for_recall",
    "classification",
    "status",
    "voluntary_mandated",
    "initial_firm_notification",
    "distribution_pattern",
    "code_info",
    "more_code_info",
    "city",
    "state",
    "country",
    "address_1",
    "address_2",
    "postal_code",
    "product_type",
    "recall_initiation_date",
    "center_classification_date",
    "termination_date",
    "report_date",
]


def _parse_date(value: str | None) -> str | None:
    """Normalize openFDA's YYYYMMDD dates to ISO-8601, or None."""
    if not value:
        return None
    value = str(value).strip()
    if re.fullmatch(r"\d{8}", value):
        try:
            return datetime.strptime(value, "%Y%m%d").date().isoformat()
        except ValueError:
            return value
    return value


def normalize_record(raw: dict) -> dict:
    """Project an openFDA enforcement record into our canonical shape."""
    rec: dict = {k: raw.get(k) for k in KEEP_FIELDS}

    # Normalize date fields.
    for field in (
        "recall_initiation_date",
        "center_classification_date",
        "termination_date",
        "report_date",
    ):
        rec[field] = _parse_date(rec.get(field))

    # A stable, human-friendly id. event_id is unique per openFDA record.
    rec["id"] = str(raw.get("event_id") or raw.get("recall_number") or "")

    # Severity rank for sorting/filtering (Class I = most severe).
    cls = (rec.get("classification") or "").upper()
    rec["severity_rank"] = {"CLASS I": 1, "CLASS II": 2, "CLASS III": 3}.get(cls, 4)

    # Bookkeeping.
    rec["_first_seen"] = datetime.now(timezone.utc).isoformat()
    rec["_last_updated"] = rec["_first_seen"]
    rec["_enrich_attempts"] = 0
    rec["_enriched"] = False

    return rec


# --- Tavily Pro Research output schema -------------------------------------
# This is the JSON Schema Tavily uses to structure its research output. It
# drives the "dense understanding" of each recall: who the company is, what
# brands they own, their recall history, and reporting-controls red flags.
ENRICHMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "parent_company": {
            "type": "string",
            "description": "The ultimate parent company of the recalling firm, if determinable.",
        },
        "brands": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Consumer-facing brand names owned by or associated with this company.",
        },
        "severity_summary": {
            "type": "string",
            "description": "Plain-language summary of the health risk and severity of this recall.",
        },
        "contaminant_or_cause": {
            "type": "string",
            "description": "The specific contaminant, allergen, or defect causing the recall (e.g. Listeria monocytogenes, undeclared peanut).",
        },
        "affected_states": {
            "type": "array",
            "items": {"type": "string"},
            "description": "US states where the recalled product was distributed, if known.",
        },
        "recall_history": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "year": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["year", "summary"],
            },
            "description": "Notable prior recalls involving this company or its brands.",
        },
        "reporting_controls_red_flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Indicators of weak food-safety reporting or oversight: late disclosure, repeat violations, inspection failures, lack of traceability, etc.",
        },
        "avoid_guidance": {
            "type": "string",
            "description": "Concrete guidance for consumers/agents on what to avoid and why.",
        },
    },
    "required": [
        "parent_company",
        "brands",
        "severity_summary",
        "contaminant_or_cause",
        "recall_history",
        "reporting_controls_red_flags",
        "avoid_guidance",
    ],
}


def build_enrichment_prompt(rec: dict) -> str:
    """Build the research prompt for a single recall record."""
    firm = rec.get("recalling_firm") or "an unknown firm"
    product = rec.get("product_description") or "an unspecified product"
    reason = rec.get("reason_for_recall") or "an unspecified reason"
    classification = rec.get("classification") or "unspecified class"
    distribution = rec.get("distribution_pattern") or "unknown distribution"
    code_info = rec.get("code_info") or ""

    return (
        f"Research this active US food recall and produce a dense, decision-ready profile.\n\n"
        f"Recalling firm: {firm}\n"
        f"Product: {product}\n"
        f"Reason for recall: {reason}\n"
        f"FDA classification: {classification}\n"
        f"Distribution: {distribution}\n"
        f"Codes (UPC/lot): {code_info}\n\n"
        "Focus on: the parent company and its brand portfolio, the specific "
        "contaminant or cause, the health severity, which states are affected, "
        "the company's prior recall history, and any red flags about weak "
        "food-safety reporting or oversight controls. Cite authoritative "
        "sources (FDA, USDA/FSIS, CDC, company press releases)."
    )
