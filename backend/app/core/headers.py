"""Security headers the app adds to every response.

NGINX in front of production already sends HSTS, X-Content-Type-Options, X-Frame-Options and
Referrer-Policy, so those aren't repeated here (duplicated headers can conflict). The SPA build
loads only same-origin scripts and styles; Vue sets some inline styles, hence 'unsafe-inline' for
style-src only. Cloudflare injects its Web Analytics beacon at the edge: the script comes from
static.cloudflareinsights.com and posts to cloudflareinsights.com/cdn-cgi/rum. Swagger UI at /api/docs loads its assets from a CDN, so it gets no CSP.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' https://static.cloudflareinsights.com",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self' data:",
        "connect-src 'self' https://cloudflareinsights.com",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
    ]
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
_NO_CSP_PATHS = ("/api/docs",)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith(_NO_CSP_PATHS):
            response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response
