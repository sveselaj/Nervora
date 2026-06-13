"""Authentication: token verification abstraction + identity model.

Two verifier implementations sit behind one interface:

* ``DevTokenVerifier``   — HS256, symmetric secret. LOCAL DEVELOPMENT ONLY.
* ``EntraOIDCVerifier``  — RS256, validates Azure Entra ID tokens against the
                            tenant JWKS. The production path.

The rest of the system depends only on :class:`TokenVerifier` and
:class:`Principal`, so swapping dev → Entra is a single wiring change.
"""

from auth.identity import Principal
from auth.tokens import (
    AuthError,
    DevTokenSigner,
    DevTokenVerifier,
    EntraOIDCVerifier,
    TokenVerifier,
    build_verifier,
)

__all__ = [
    "Principal",
    "AuthError",
    "TokenVerifier",
    "DevTokenSigner",
    "DevTokenVerifier",
    "EntraOIDCVerifier",
    "build_verifier",
]
