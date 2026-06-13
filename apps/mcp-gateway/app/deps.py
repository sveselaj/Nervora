"""FastAPI dependencies: bearer-token authentication into a Principal."""

from __future__ import annotations

from auth import AuthError, Principal
from fastapi import Header, HTTPException, Request


def get_principal(request: Request, authorization: str = Header(default="")) -> Principal:
    """Validate the bearer token and return the caller :class:`Principal`.

    Authentication failures are 401. This runs the configured verifier (dev
    HS256 locally, Entra ID JWKS in production) — the route handler never sees
    a token, only a verified principal.
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    verifier = request.app.state.verifier
    try:
        from telemetry import span

        with span("auth.validate"):
            return verifier.verify(token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc),
                            headers={"WWW-Authenticate": "Bearer"}) from exc
