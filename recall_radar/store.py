"""JSON-backed store for recall records.

The single source of truth is `data/recalls.json` — a committed, human-readable
artifact. This keeps the repo dependency-free (no SQLite binary bloat), makes
nightly diffs clean and reviewable in git, and lets the MCP server load the
whole dataset into memory in one read.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import config


def load() -> dict:
    """Load the dataset. Returns {"generated_at": ..., "recalls": [...]}."""
    if not config.JSON_PATH.exists():
        return {"generated_at": None, "recalls": []}
    with config.JSON_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save(dataset: dict) -> None:
    """Atomically write the dataset to disk."""
    config.JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.JSON_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    tmp.replace(config.JSON_PATH)


def build_dataset(recalls: list[dict]) -> dict:
    """Wrap a list of recall records into the canonical dataset envelope."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(recalls),
        "recalls": recalls,
    }
