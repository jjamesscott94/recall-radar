"""Tavily Pro Research client.

Implements the two-step research contract:
  1. POST /research            -> 201 {request_id, status: "pending"}
  2. GET  /research/{id}       -> 202 while pending/in_progress,
                                  200 when done {status, content, sources}

When an `output_schema` is supplied, `content` comes back as a structured
object matching that schema (instead of a markdown string).
"""

import time

import httpx

from . import config


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.TAVILY_API_KEY}",
        "Content-Type": "application/json",
    }


def create_research(
    input_text: str,
    output_schema: dict | None = None,
    model: str | None = None,
    include_domains: list[str] | None = None,
) -> str:
    """Queue a research task and return its request_id."""
    payload: dict = {
        "input": input_text,
        "model": model or config.TAVILY_MODEL,
        "stream": False,
    }
    if output_schema:
        payload["output_schema"] = output_schema
    if include_domains:
        payload["include_domains"] = include_domains

    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{config.TAVILY_BASE_URL}/research", json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

    return data["request_id"]


def get_research(request_id: str) -> dict:
    """Poll a research task's status. Returns the raw JSON body."""
    with httpx.Client(timeout=60) as client:
        resp = client.get(f"{config.TAVILY_BASE_URL}/research/{request_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def run_research(
    input_text: str,
    output_schema: dict | None = None,
    model: str | None = None,
    include_domains: list[str] | None = None,
    poll_interval: float = 5.0,
    max_wait: float = 600.0,
) -> tuple[object, list[dict]]:
    """Queue + poll a research task to completion.

    Returns (content, sources). `content` is a structured object when
    `output_schema` is provided, otherwise a markdown string.
    """
    request_id = create_research(input_text, output_schema, model, include_domains)
    deadline = time.time() + max_wait

    while time.time() < deadline:
        data = get_research(request_id)
        status = data.get("status")

        if status == "completed":
            return data.get("content"), data.get("sources", [])
        if status == "failed":
            raise RuntimeError(f"Tavily research failed for request {request_id}")

        time.sleep(poll_interval)

    raise TimeoutError(f"Tavily research timed out for request {request_id}")
