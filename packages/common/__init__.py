"""Cross-cutting primitives shared by every service (settings, ids, time).

Kept deliberately tiny: no business logic lives here, only the wiring that
both the gateway and the worker need to agree on.
"""

from common.ids import gen_idempotency_key, gen_request_id, gen_trace_id, sha256_hex
from common.settings import Settings, get_settings

__all__ = [
    "Settings",
    "get_settings",
    "gen_request_id",
    "gen_trace_id",
    "gen_idempotency_key",
    "sha256_hex",
]
