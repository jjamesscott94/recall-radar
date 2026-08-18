"""Per-IP rate limiting for the hosted (streamable-http) MCP transport.

A pure-ASGI middleware (deliberately NOT Starlette's ``BaseHTTPMiddleware``,
which buffers responses and can break SSE streaming) that enforces a
sliding-window request cap per client IP. This bounds the cost of a public
endpoint: a flood gets 429'd before it can rack up Cloud Run compute. The
Tavily enrichment path is never reachable from here anyway — it only runs
inside the nightly workflow.

Client IP resolution: Cloud Run's frontend appends the real client IP to
``X-Forwarded-For``, so we take the RIGHTMOST value (the leftmost is
client-spoofable). Falls back to the socket peer address for non-proxied
deployments.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque

from starlette.responses import JSONResponse


class RateLimitMiddleware:
    """Sliding-window per-IP rate limiter (pure ASGI)."""

    def __init__(
        self,
        app,
        max_requests: int = 60,
        window_seconds: int = 60,
        max_tracked_ips: int = 10_000,
    ) -> None:
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_tracked_ips = max_tracked_ips
        # ip -> deque of monotonic timestamps, LRU-ordered for bounded memory.
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ip = self._client_ip(scope)
        if not self._allow(ip):
            response = JSONResponse(
                {
                    "error": "rate limit exceeded",
                    "retry_after_seconds": self.window_seconds,
                },
                status_code=429,
                headers={"Retry-After": str(self.window_seconds)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _client_ip(self, scope) -> str:
        headers = dict(scope.get("headers") or [])
        xff = headers.get(b"x-forwarded-for")
        if xff:
            # Rightmost value is the real client IP appended by the proxy.
            return xff.decode("latin-1").split(",")[-1].strip() or "unknown"
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _allow(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            # Re-insert at the end so the OrderedDict stays LRU-ordered.
            q = self._hits.pop(ip, None)
            if q is None:
                while len(self._hits) >= self.max_tracked_ips:
                    self._hits.popitem(last=False)
                q = deque()
            self._hits[ip] = q

            # Drop timestamps outside the window.
            while q and now - q[0] > self.window_seconds:
                q.popleft()

            if len(q) >= self.max_requests:
                return False
            q.append(now)
            return True
