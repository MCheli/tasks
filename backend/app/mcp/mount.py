"""Put the MCP connector into the FastAPI app.

The SDK can build a whole Starlette app, but mounting that at "/" would swallow the SPA's
catch-all, so the pieces are added to the FastAPI router one by one, before the SPA fallback:

- /mcp: the streamable HTTP transport (stateless, JSON responses: two uvicorn workers share no
  memory, so a session pinned to one worker would break), wrapped in the SDK's bearer-token
  middleware. No token -> 401 with WWW-Authenticate pointing at the resource metadata.
- /authorize, /token, /register, /revoke and /.well-known/oauth-authorization-server: the
  authorization server (app/mcp/oauth.py).
- /.well-known/oauth-protected-resource/mcp: the protected-resource metadata (RFC 9728).

`lifespan()` runs the transport's session manager; main.py enters it inside the app lifespan.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.provider import ProviderTokenVerifier
from mcp.server.auth.routes import (
    build_resource_metadata_url,
    create_auth_routes,
    create_protected_resource_routes,
)
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import Route

from app.config import settings
from app.mcp.oauth import provider
from app.mcp.server import build_auth_settings, mcp

logger = logging.getLogger("tasks.mcp")

MCP_PATH = "/mcp"

_session_manager: StreamableHTTPSessionManager | None = None


def install(app: FastAPI) -> None:
    """Add the connector's routes to `app`. No-op unless settings.mcp_enabled."""
    global _session_manager
    if not settings.mcp_enabled:
        logger.info("MCP connector not mounted (TASKS_PUBLIC_URL unset or demo mode).")
        return

    auth = build_auth_settings()
    verifier = ProviderTokenVerifier(provider)

    _session_manager = StreamableHTTPSessionManager(
        app=mcp._lowlevel_server,  # noqa: SLF001  (the SDK exposes no public accessor)
        json_response=True,
        stateless=True,
        # nginx already pins the Host header to the public name.
        security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    endpoint = AuthenticationMiddleware(
        AuthContextMiddleware(
            RequireAuthMiddleware(
                StreamableHTTPASGIApp(_session_manager),
                auth.required_scopes or [],
                build_resource_metadata_url(auth.resource_server_url),  # type: ignore[arg-type]
            )
        ),
        backend=BearerAuthBackend(verifier),
    )

    routes: list[Route] = [Route(MCP_PATH, endpoint=endpoint)]
    routes.extend(
        create_auth_routes(
            provider=provider,
            issuer_url=auth.issuer_url,
            client_registration_options=auth.client_registration_options,
            revocation_options=auth.revocation_options,
        )
    )
    routes.extend(
        create_protected_resource_routes(
            resource_url=auth.resource_server_url,  # type: ignore[arg-type]
            authorization_servers=[auth.issuer_url],
            scopes_supported=auth.required_scopes,
            resource_name="Tasks",
        )
    )
    for route in routes:
        app.router.routes.append(route)
    logger.info("MCP connector mounted at %s (issuer %s)", MCP_PATH, auth.issuer_url)


@asynccontextmanager
async def lifespan():
    """Run the transport's session manager for the app's lifetime (no-op when not mounted)."""
    if _session_manager is None:
        yield
        return
    async with _session_manager.run():
        yield
