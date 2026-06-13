"""PII redaction."""

from pii import redact, redact_text


def test_declared_sensitive_fields_masked():
    data = {"name": "Anika", "salary": 118000, "email": "a@example.com"}
    res = redact(data, sensitive_fields={"salary", "email"})
    assert res.data["salary"] == "***REDACTED***"
    assert res.data["email"] == "***REDACTED***"
    assert res.data["name"] == "Anika"
    assert set(res.redacted_fields) == {"salary", "email"}
    assert res.status == "redacted"


def test_pattern_sweep_catches_free_text_pii():
    data = {"note": "contact me at john.doe@corp.com or +49 151 23456789"}
    res = redact(data, sensitive_fields=set())
    assert "***REDACTED***" in res.data["note"]
    assert "email" in res.matched_patterns


def test_allow_raw_skips_field_masking_but_keeps_sweep():
    data = {"salary": 118000, "note": "iban DE89370400440532013000"}
    res = redact(data, sensitive_fields={"salary"}, allow_raw=True)
    assert res.data["salary"] == 118000  # raw allowed
    assert "***REDACTED***" in res.data["note"]  # sweep still runs


def test_nested_structures():
    data = {"employee": {"profile": {"national_id": "123-45-6789"}}}
    res = redact(data, sensitive_fields={"national_id"})
    assert res.data["employee"]["profile"]["national_id"] == "***REDACTED***"


def test_redact_text_clean_string_unchanged():
    out, matched = redact_text("nothing sensitive here")
    assert out == "nothing sensitive here" and matched == []
