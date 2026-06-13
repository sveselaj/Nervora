"""Identifier and hashing helpers.

`trace_id` / `request_id` are W3C-friendly hex ids so they line up with
OpenTelemetry traces. Input hashing is SHA-256 so audit records can prove
*what* was requested without storing the (possibly sensitive) payload.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def gen_request_id() -> str:
    return uuid.uuid4().hex


def gen_trace_id() -> str:
    # 32 hex chars == 128-bit trace id, matching the OTel/W3C trace format.
    return uuid.uuid4().hex


def gen_idempotency_key() -> str:
    return f"idk_{uuid.uuid4().hex}"


def sha256_hex(payload: Any) -> str:
    """Stable SHA-256 of an arbitrary JSON-serialisable payload.

    Keys are sorted so semantically-identical inputs hash identically — this
    is what lets the worker detect duplicate submissions.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
