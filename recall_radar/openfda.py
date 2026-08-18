"""openFDA food/enforcement client.

The `food/enforcement` endpoint is the authoritative, free, keyless source for
US food recalls. It covers BOTH FDA-regulated food and USDA/FSIS-regulated
meat & poultry (FSIS recalls flow into openFDA), so a single source is
complete. We pull only `status:Ongoing` records — the currently-active set.
"""

import httpx

from . import config


def fetch_active_recalls() -> list[dict]:
    """Fetch all currently-active (Ongoing) food enforcement recalls.

    Paginates through openFDA (max 1000 per page) until the full active set is
    collected. Returns the raw openFDA records.
    """
    records: list[dict] = []
    skip = 0
    limit = 1000

    with httpx.Client(timeout=60) as client:
        while True:
            params = {
                "search": "status:Ongoing",
                "limit": limit,
                "skip": skip,
            }
            resp = client.get(config.OPENFDA_BASE_URL + config.OPENFDA_ENDPOINT, params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            records.extend(results)

            total = data.get("meta", {}).get("results", {}).get("total", 0)
            skip += len(results)
            if not results or skip >= total:
                break

    return records
