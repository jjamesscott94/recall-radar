# Security Policy

Recall Radar is a public, read-only intelligence service. This document
describes how secrets, spend, and abuse are handled so you can share the repo
and the hosted endpoint with confidence.

## Secrets

- **The Tavily API key is never committed.** It lives only in:
  - GitHub Actions secrets (`TAVILY_API_KEY`), encrypted at rest;
  - Google Secret Manager (`recall-radar-github-token`), for the scheduler
    trigger function;
  - your local environment (`.env` / `.env.local`, both gitignored).
- `.env.example` contains placeholders only — no real values.
- The committed `data/recalls.json` contains recall data only; it is scanned
  for credential-shaped strings as part of review and contains none.

## Cost & abuse posture

The expensive path (Tavily Pro Research) is **not reachable from the public
endpoint**. It runs only inside the nightly GitHub Actions workflow, which is
triggered exclusively by a locked-down Cloud Function.

| Surface | Public? | What abuse costs |
|---|---|---|
| Hosted MCP endpoint (Cloud Run) | Yes | Read-only compute only — no Tavily, no writes |
| Trigger Cloud Function | No (OIDC-only, 403 otherwise) | Nothing |
| GitHub Actions workflow | No (`workflow_dispatch` only) | Nothing |
| Tavily enrichment | No (inside the workflow) | The only spend — bounded below |

Defense in depth:

1. **Rate limiting** — the hosted endpoint enforces a per-IP sliding-window
   cap (`RECALL_RADAR_RATE_LIMIT_REQUESTS` per
   `RECALL_RADAR_RATE_LIMIT_WINDOW` seconds, default 60/min). Floods get
   `429` before they rack up compute.
2. **`maxScale=1`** — the Cloud Run service is capped at a single instance,
   bounding worst-case compute.
3. **Spend guard** — `RECALL_RADAR_MAX_ENRICH` (default 10) caps enrichments
   per run; the budget decrements on *every* attempt (success or failure), and
   requests are spaced to stay under Tavily's rate limit.
4. **Cheap model default** — `TAVILY_MODEL` defaults to `mini` (4–110
   credits/request) rather than `pro` (15–250), cutting enrichment cost ~4×.
5. **Every-other-day schedule** — the pipeline runs on odd days of the month
   (08:00 UTC), halving monthly Tavily spend.

## Reporting a vulnerability

Open an issue at https://github.com/jjamesscott94/recall-radar/issues, or
contact the maintainer directly. Please do not disclose a suspected secret
leak publicly — report it privately first.
