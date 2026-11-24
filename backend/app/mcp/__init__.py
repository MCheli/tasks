"""The Tasks MCP connector: https://<app>/mcp plus its OAuth 2.1 authorization server.

- oauth.py: the authorization-server provider (dynamic client registration, PKCE codes,
  opaque tokens in Postgres) and the Google sign-in leg, restricted to the allowlisted account.
- server.py: the MCP server and its tools (list/get/create/update/complete/reopen/add_note).
- mount.py: puts the routes into the FastAPI app (/mcp, /authorize, /token, /register,
  /revoke and the two .well-known documents) and runs the transport in the app's lifespan.
"""
