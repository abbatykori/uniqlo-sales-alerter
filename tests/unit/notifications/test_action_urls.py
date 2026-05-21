"""HMAC sign/verify round-trip, tamper rejection, expiry handling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from uniqlo_sales_alerter.notifications.action_urls import (
    ActionURLExpired,
    ActionURLInvalid,
    sign_action,
    verify_action,
)

_SECRET = "0123456789abcdef" * 4


def _qs_dict(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_empty_server_url_returns_empty_string() -> None:
    assert sign_action(
        secret=_SECRET, base_url="", action="ignore", path_arg="E001"
    ) == ""


def test_empty_secret_returns_empty_string() -> None:
    assert sign_action(
        secret="", base_url="http://x", action="ignore", path_arg="E001"
    ) == ""


def test_round_trip_ignore() -> None:
    url = sign_action(
        secret=_SECRET,
        base_url="http://localhost:8000",
        action="ignore",
        path_arg="E001",
        payload={"name": "Soft Tee"},
    )
    assert url.startswith("http://localhost:8000/actions/ignore/E001?")
    params = _qs_dict(url)
    verified = verify_action(secret=_SECRET, query_params=params)
    assert verified.payload == {"name": "Soft Tee"}


def test_round_trip_watch_with_color_and_size() -> None:
    url = sign_action(
        secret=_SECRET,
        base_url="http://localhost",
        action="watch",
        path_arg="E001",
        payload={"color": "09", "size": "002"},
    )
    params = _qs_dict(url)
    verified = verify_action(secret=_SECRET, query_params=params)
    assert verified.payload == {"color": "09", "size": "002"}


def test_round_trip_snooze() -> None:
    url = sign_action(
        secret=_SECRET,
        base_url="http://localhost",
        action="snooze",
        payload={"filter_id": "7", "duration": "7d"},
    )
    params = _qs_dict(url)
    verified = verify_action(secret=_SECRET, query_params=params)
    assert verified.payload == {"filter_id": "7", "duration": "7d"}


def test_tampered_payload_rejected() -> None:
    url = sign_action(
        secret=_SECRET,
        base_url="http://x",
        action="ignore",
        path_arg="E001",
        payload={"name": "Original"},
    )
    params = _qs_dict(url)
    params["name"] = "Tampered"
    with pytest.raises(ActionURLInvalid, match="signature mismatch"):
        verify_action(secret=_SECRET, query_params=params)


def test_swapped_signature_rejected() -> None:
    url_a = sign_action(
        secret=_SECRET, base_url="http://x", action="ignore",
        path_arg="E001", payload={"name": "A"},
    )
    url_b = sign_action(
        secret=_SECRET, base_url="http://x", action="ignore",
        path_arg="E002", payload={"name": "B"},
    )
    params_a = _qs_dict(url_a)
    params_b = _qs_dict(url_b)
    # Cross-graft signatures.
    params_a["sig"] = params_b["sig"]
    with pytest.raises(ActionURLInvalid, match="signature mismatch"):
        verify_action(secret=_SECRET, query_params=params_a)


def test_missing_sig_rejected() -> None:
    with pytest.raises(ActionURLInvalid, match="missing sig"):
        verify_action(
            secret=_SECRET,
            query_params={"name": "X", "exp": "9999999999"},
        )


def test_missing_exp_rejected() -> None:
    with pytest.raises(ActionURLInvalid, match="missing sig or exp"):
        verify_action(
            secret=_SECRET,
            query_params={"name": "X", "sig": "deadbeef"},
        )


def test_non_integer_exp_rejected() -> None:
    with pytest.raises(ActionURLInvalid, match="exp is not an integer"):
        verify_action(
            secret=_SECRET,
            query_params={"name": "X", "exp": "soon", "sig": "x"},
        )


def test_expired_url_raises_expired() -> None:
    past = datetime.now(timezone.utc) - timedelta(days=400)
    url = sign_action(
        secret=_SECRET, base_url="http://x", action="ignore",
        path_arg="E001", payload={"name": "X"},
        now=past, ttl_days=30,
    )
    params = _qs_dict(url)
    with pytest.raises(ActionURLExpired):
        verify_action(secret=_SECRET, query_params=params)


def test_wrong_secret_rejected() -> None:
    url = sign_action(
        secret=_SECRET, base_url="http://x", action="ignore",
        path_arg="E001", payload={"name": "X"},
    )
    params = _qs_dict(url)
    with pytest.raises(ActionURLInvalid, match="signature mismatch"):
        verify_action(secret="other-secret", query_params=params)


def test_unset_server_secret_rejects() -> None:
    with pytest.raises(ActionURLInvalid, match="server secret is unset"):
        verify_action(secret="", query_params={"sig": "x", "exp": "9999999999"})


def test_default_ttl_is_30_days() -> None:
    now = datetime.now(timezone.utc)
    url = sign_action(
        secret=_SECRET, base_url="http://x", action="ignore",
        path_arg="E001", payload={}, now=now,
    )
    exp_str = _qs_dict(url)["exp"]
    expected = int((now + timedelta(days=30)).timestamp())
    # Allow 1 second of rounding wobble
    assert abs(int(exp_str) - expected) <= 1


def test_custom_ttl_respected() -> None:
    url = sign_action(
        secret=_SECRET, base_url="http://x", action="ignore",
        path_arg="E001", payload={}, ttl_days=1,
    )
    params = _qs_dict(url)
    verified = verify_action(secret=_SECRET, query_params=params)
    # Within ~24h of now
    age = (verified.expires_at - datetime.now(timezone.utc)).total_seconds()
    assert 86399 <= age <= 86401


def test_canonical_form_independent_of_payload_order() -> None:
    """The signature must be identical regardless of dict insertion order."""
    a = sign_action(
        secret=_SECRET, base_url="http://x", action="ignore",
        path_arg="E001",
        payload={"name": "X", "color": "09"},
        now=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    b = sign_action(
        secret=_SECRET, base_url="http://x", action="ignore",
        path_arg="E001",
        payload={"color": "09", "name": "X"},
        now=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    assert _qs_dict(a)["sig"] == _qs_dict(b)["sig"]


def test_special_characters_in_payload_round_trip() -> None:
    """Names with spaces and slashes must round-trip cleanly."""
    url = sign_action(
        secret=_SECRET, base_url="http://x", action="ignore",
        path_arg="E001",
        payload={"name": "Soft Tee (Slim Fit) /  XL"},
    )
    params = _qs_dict(url)
    verified = verify_action(secret=_SECRET, query_params=params)
    assert verified.payload["name"] == "Soft Tee (Slim Fit) /  XL"


def test_replay_is_idempotent_by_design() -> None:
    """A signed URL verifies repeatedly until expiry — the handler must dedupe."""
    url = sign_action(
        secret=_SECRET, base_url="http://x", action="ignore",
        path_arg="E001", payload={"name": "X"},
    )
    params = _qs_dict(url)
    verify_action(secret=_SECRET, query_params=params)
    verify_action(secret=_SECRET, query_params=params)
    verify_action(secret=_SECRET, query_params=params)
