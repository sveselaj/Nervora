"""Token signing/verification: dev (HS256) and Entra ID (RS256/JWKS)."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import jwt
from jwt import PyJWKClient

from auth.identity import Principal


class AuthError(Exception):
    """Raised when a token is missing, malformed, expired, or untrusted."""

    def __init__(self, message: str, code: str = "AUTH_INVALID_TOKEN") -> None:
        super().__init__(message)
        self.code = code


def _principal_from_claims(claims: dict[str, Any]) -> Principal:
    role = claims.get("agent_role") or claims.get("role") or ""
    agent_id = claims.get("agent_id") or claims.get("azp") or claims.get("sub", "")
    scopes_claim = claims.get("scp") or claims.get("scope") or ""
    if isinstance(scopes_claim, str):
        scopes = tuple(s for s in scopes_claim.split() if s)
    else:
        scopes = tuple(scopes_claim)
    if not role:
        raise AuthError("token is missing the agent_role claim", code="AUTH_NO_ROLE")
    return Principal(
        subject=claims.get("sub", ""),
        agent_id=agent_id,
        role=role,
        scopes=scopes,
        tenant_id=claims.get("tid", ""),
        raw_claims=claims,
    )


class TokenVerifier(ABC):
    """Verify a bearer token and return a :class:`Principal`."""

    @abstractmethod
    def verify(self, token: str) -> Principal: ...


class DevTokenSigner:
    """Mint HS256 test tokens. LOCAL DEVELOPMENT ONLY — never used in prod.

    Mirrors the claim shape Entra ID would emit so the gateway code path is
    identical regardless of which verifier is wired in.
    """

    def __init__(self, secret: str, audience: str = "api://secure-mcp-gateway") -> None:
        self._secret = secret
        self._audience = audience

    def mint(
        self,
        *,
        subject: str,
        agent_id: str,
        role: str,
        scopes: list[str] | None = None,
        ttl_seconds: int = 3600,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": "dev-token-signer",
            "aud": self._audience,
            "sub": subject,
            "agent_id": agent_id,
            "agent_role": role,
            "scp": " ".join(scopes or []),
            "iat": now,
            "nbf": now,
            "exp": now + ttl_seconds,
        }
        return jwt.encode(claims, self._secret, algorithm="HS256")


class DevTokenVerifier(TokenVerifier):
    """Verify HS256 dev tokens. LOCAL DEVELOPMENT ONLY."""

    def __init__(self, secret: str, audience: str = "api://secure-mcp-gateway") -> None:
        self._secret = secret
        self._audience = audience

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=self._audience,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("token expired", code="AUTH_TOKEN_EXPIRED") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"invalid token: {exc}") from exc
        return _principal_from_claims(claims)


class EntraOIDCVerifier(TokenVerifier):
    """Validate Azure Entra ID access tokens (RS256) against tenant JWKS.

    Production path. Performs signature verification using the rotating signing
    keys published at the tenant ``jwks_uri``, plus issuer and audience checks.
    See ``docs/security-model.md`` for the full validation contract.
    """

    def __init__(self, *, jwks_url: str, issuer: str, audience: str) -> None:
        if not (jwks_url and issuer and audience):
            raise AuthError(
                "Entra verifier requires jwks_url, issuer and audience",
                code="AUTH_MISCONFIGURED",
            )
        self._issuer = issuer
        self._audience = audience
        # PyJWKClient caches and refreshes the signing keys for us.
        self._jwk_client = PyJWKClient(jwks_url)

    def verify(self, token: str) -> Principal:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("token expired", code="AUTH_TOKEN_EXPIRED") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"invalid Entra token: {exc}") from exc
        except Exception as exc:  # JWKS fetch / key resolution failures
            raise AuthError(f"token key resolution failed: {exc}", code="AUTH_JWKS") from exc
        return _principal_from_claims(claims)


def build_verifier(settings) -> TokenVerifier:
    """Select the verifier implementation from settings."""
    if settings.auth_mode == "entra":
        return EntraOIDCVerifier(
            jwks_url=settings.entra_jwks_url,
            issuer=settings.entra_issuer,
            audience=settings.entra_audience,
        )
    return DevTokenVerifier(
        secret=settings.dev_token_signing_secret,
        audience=settings.entra_audience,
    )
