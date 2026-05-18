"""Tests for the shared rate-limiter helpers.

These cover the pure-Python helper functions (no HTTP integration) — the
actual rate-limit enforcement is exercised by slowapi's own tests. Here we
verify:

* ``is_internal_service`` reads the configured key correctly,
* limit-string constants exist and have the expected slowapi syntax.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.limiter import (
    LIMIT_ALERT_WRITE,
    LIMIT_AUTH_LOGIN,
    LIMIT_CONTROL_WRITE,
    LIMIT_MLOPS_ADMIN,
    is_internal_service,
)


def _fake_request(header_value: str | None) -> SimpleNamespace:
    headers = {"X-Service-Key": header_value} if header_value is not None else {}
    return SimpleNamespace(headers=headers)


def test_is_internal_service_true_when_key_matches(monkeypatch):
    from app import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_API_KEY", "secret-abc")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)  # required by Settings
    assert is_internal_service(_fake_request("secret-abc")) is True


def test_is_internal_service_false_when_key_missing(monkeypatch):
    from app import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_API_KEY", "secret-abc")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    assert is_internal_service(_fake_request(None)) is False


def test_is_internal_service_false_when_key_wrong(monkeypatch):
    from app import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_API_KEY", "secret-abc")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    assert is_internal_service(_fake_request("wrong-key")) is False


def test_is_internal_service_false_when_no_key_configured(monkeypatch):
    """If INTERNAL_API_KEY is unset, the helper must NOT silently exempt
    requests just because the caller happens to send any header value."""
    from app import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_API_KEY", "")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    assert is_internal_service(_fake_request("anything")) is False


@pytest.mark.parametrize(
    "limit",
    [LIMIT_AUTH_LOGIN, LIMIT_CONTROL_WRITE, LIMIT_ALERT_WRITE, LIMIT_MLOPS_ADMIN],
)
def test_limit_constants_have_slowapi_syntax(limit: str) -> None:
    # slowapi expects "<count>/<period>" — basic sanity check
    count, _, period = limit.partition("/")
    assert count.isdigit()
    assert period in {"second", "minute", "hour", "day"}
