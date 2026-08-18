"""openFDA food/enforcement client.

The `food/enforcement` endpoint is the authoritative, free, keyless source for
US food recalls. It covers BOTH FDA-regulated food and USDA/FSIS-regulated
meat & poultry (FSIS recalls flow into openFDA), so a single source is
complete. We pull only `status:Ongoing` records — the currently-active set.
"""

import time

import httpx

from . import config


def _get_with_retry(client: httpx.Client, url: str, params: dict) -> httpx.Response:
    """GET with retry/backoff for transient openFDA 5xx errors.

    openFDA occasionally returns 500s under load; a nightly job should not
    fail the whole run on a single transient error.
    """
    last_exc: Exception | None = None
    for attempt in range(config.OPENFDA_MAX_RETRIES):
        try:
            resp = client.get(url, params=params)
            if resp.status_code < 500:
                return resp
            last_exc = httpx.HTTPStatusError(
                f"openFDA {resp.status_code}", request=resp.request, response=resp
            )
        except httpx.HTTPError as exc:  # network/timeout errors
            last_exc = exc
        if attempt < config.OPENFDA_MAX_RETRIES - 1:
            time.sleep(config.OPENFDA_RETRY_BACKOFF_SECONDS * (2 ** attempt))
    raise last_exc  # type: ignore[misc]


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
            resp = _get_with_retry(client, config.OPENFDA_BASE_URL + config.OPENFDA_ENDPOINT, params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            records.extend(results)

            total = data.get("meta", {}).get("results", {}).get("total", 0)
            skip += len(results)
            if not results or skip >= total:
                break

    return records
