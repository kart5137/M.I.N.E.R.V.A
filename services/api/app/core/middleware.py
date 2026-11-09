"""Response headers added to every API response (M8 hardening).

- Security headers: the API only serves JSON (plus the /docs page), so it forbids
  framing and MIME sniffing and sends no referrer.
- Caching: data changes once a week, so successful GETs may be cached briefly by
  browsers and CDNs. Status, verification and error responses are never cached.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"cross-origin-resource-policy": b"cross-origin",
}

#: Paths whose answers must always be fresh: status checks, and reports (the list changes
#: as soon as someone generates one; verification compares against current data).
NO_STORE_SUFFIXES = ("/health", "/meta/status")
NO_STORE_PREFIXES = ("/docs", "/redoc", "/api/v1/reports")


class ResponseHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, max_age: int = 300) -> None:
        self.app = app
        self.cache_value = (f"public, max-age={max_age}, stale-while-revalidate={max_age * 2}"
                            .encode() if max_age > 0 else b"no-store")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        cacheable = (scope["method"] in ("GET", "HEAD")
                     and not path.endswith(NO_STORE_SUFFIXES)
                     and not path.startswith(NO_STORE_PREFIXES))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in SECURITY_HEADERS and k.lower() != b"cache-control"]
                headers.extend(SECURITY_HEADERS.items())
                ok = 200 <= message["status"] < 300
                headers.append((b"cache-control",
                                self.cache_value if cacheable and ok else b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
