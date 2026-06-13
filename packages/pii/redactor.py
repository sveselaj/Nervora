"""Field-level + pattern-based redaction.

Two layers:

1. **Declared fields** — a tool result can mark keys as sensitive (e.g.
   ``salary``, ``national_id``). Those are masked unless ``allow_raw`` is set.
2. **Pattern sweep** — every remaining string value is scanned for common PII
   patterns (email, phone, IBAN, credit-card/SSN-like digits) as defence in
   depth against leakage through free-text fields.

Redaction is deterministic and side-effect free, so it is safe to wrap in a
span and to unit test exhaustively.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

MASK = "***REDACTED***"

_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    "phone": re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"),
    "ssn_like": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
}


@dataclass
class RedactionResult:
    data: Any
    redacted_fields: list[str] = field(default_factory=list)
    matched_patterns: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if not self.redacted_fields and not self.matched_patterns:
            return "none"
        return "redacted"


def redact_text(text: str) -> tuple[str, list[str]]:
    """Apply the pattern sweep to a single string. Returns (text, matched)."""
    matched: list[str] = []
    out = text
    for name, pattern in _PATTERNS.items():
        if pattern.search(out):
            matched.append(name)
            out = pattern.sub(MASK, out)
    return out, matched


def redact(
    data: Any,
    *,
    sensitive_fields: set[str] | None = None,
    allow_raw: bool = False,
) -> RedactionResult:
    """Recursively redact ``data``.

    ``sensitive_fields`` are masked by key name. When ``allow_raw`` is True the
    field masking is skipped (policy permitted raw PII) but the pattern sweep
    still runs as a safety net.
    """
    sensitive_fields = sensitive_fields or set()
    result = RedactionResult(data=None)

    def _walk(node: Any, key: str | None = None) -> Any:
        if isinstance(node, dict):
            return {k: _walk(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v, key) for v in node]
        if isinstance(node, str):
            if key is not None and key in sensitive_fields and not allow_raw:
                if key not in result.redacted_fields:
                    result.redacted_fields.append(key)
                return MASK
            new, matched = redact_text(node)
            for m in matched:
                if m not in result.matched_patterns:
                    result.matched_patterns.append(m)
            return new
        # Non-string sensitive values (e.g. numeric salary) are still masked.
        if key is not None and key in sensitive_fields and not allow_raw:
            if key not in result.redacted_fields:
                result.redacted_fields.append(key)
            return MASK
        return node

    result.data = _walk(data)
    return result
