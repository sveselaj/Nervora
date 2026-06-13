"""PII detection + redaction applied before any tool output is model-visible.

The gateway calls :func:`redact` on every tool result. Fields a tool marks as
sensitive are redacted unless the tool's policy (and the caller's role) allow
raw access. Regex sweeps catch common identifiers (email, phone, IBAN, SSN-like
numbers) that may leak through free-text fields.
"""

from pii.redactor import RedactionResult, redact, redact_text

__all__ = ["RedactionResult", "redact", "redact_text"]
