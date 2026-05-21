"""HMAC-signed action URLs for notification action chips.

Signed URLs let a user act on a deal a week after it arrived in their
inbox: Ignore, Watch a variant, Unwatch a variant, Snooze a filter. The
signature is computed over the canonical query string and embedded as the
``sig`` parameter. An ``exp`` Unix timestamp guarantees URLs auto-expire.

Canonical form (deterministic, sortable, replay-safe):

    1. Collect all query-string params except ``sig``.
    2. Sort by key, then by value (stable).
    3. URL-encode key=value pairs with ``urllib.parse.urlencode`` using
       ``quote_via=quote`` so all special characters round-trip.
    4. The bytes signed are exactly the canonical string above.

Both signer and verifier use the same routine; mismatches reject.
``hmac.compare_digest`` provides constant-time comparison so timing
side-channels don't leak.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from urllib.parse import quote, urlencode

DEFAULT_TTL_DAYS = 30


def _canonical_qs(params: dict[str, str]) -> str:
    """Build the canonical sorted query string used for signature input."""
    items = sorted(((k, str(v)) for k, v in params.items() if k != "sig"))
    return urlencode(items, quote_via=quote)


def _compute_sig(secret: str, params: dict[str, str]) -> str:
    canonical = _canonical_qs(params)
    mac = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), sha256)
    return mac.hexdigest()


def sign_action(
    *,
    secret: str,
    base_url: str,
    action: str,
    path_arg: str = "",
    payload: dict[str, str] | None = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
    now: datetime | None = None,
) -> str:
    """Build a signed URL of the form
    ``{base_url}/actions/{action}/{path_arg}?<canonical-qs>&exp=<unix>&sig=<hmac>``.

    Empty *base_url* or empty *secret* returns ``""`` so templates can
    detect the "no action URLs available" state.
    """
    if not base_url or not secret:
        return ""

    now = now or datetime.now(timezone.utc)
    expiry = int((now + timedelta(days=ttl_days)).timestamp())

    qs_params: dict[str, str] = dict(payload or {})
    qs_params["exp"] = str(expiry)

    sig = _compute_sig(secret, qs_params)
    qs_params["sig"] = sig

    # Build query string preserving the sort order plus a stable sig position.
    canonical = _canonical_qs(qs_params)
    canonical += f"&sig={sig}"

    path = f"/actions/{action}"
    if path_arg:
        path += f"/{quote(path_arg, safe='')}"
    return f"{base_url.rstrip('/')}{path}?{canonical}"


@dataclass(frozen=True, slots=True)
class VerifiedAction:
    """Result of a successful signature verification."""

    payload: dict[str, str]
    expires_at: datetime


class ActionURLError(Exception):
    """Base class for signature verification failures."""


class ActionURLExpired(ActionURLError):
    """The ``exp`` timestamp is in the past."""


class ActionURLInvalid(ActionURLError):
    """Missing ``sig`` / ``exp`` or signature mismatch."""


def verify_action(
    *,
    secret: str,
    query_params: dict[str, str],
    now: datetime | None = None,
) -> VerifiedAction:
    """Verify a request's ``sig`` and ``exp`` against the given *secret*.

    Pass the FastAPI request's ``request.query_params`` (which behaves
    like a dict but with multi-value semantics — call ``dict(...)`` first).

    Raises :class:`ActionURLInvalid` on bad / missing signature and
    :class:`ActionURLExpired` when the timestamp is in the past.
    """
    if not secret:
        raise ActionURLInvalid("server secret is unset")

    provided_sig = query_params.get("sig")
    exp_raw = query_params.get("exp")
    if not provided_sig or not exp_raw:
        raise ActionURLInvalid("missing sig or exp parameter")

    try:
        exp_unix = int(exp_raw)
    except ValueError as e:
        raise ActionURLInvalid("exp is not an integer") from e

    now = now or datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(exp_unix, tz=timezone.utc)
    if expires_at < now:
        raise ActionURLExpired(f"expired at {expires_at.isoformat()}")

    expected = _compute_sig(secret, query_params)
    if not hmac.compare_digest(expected, provided_sig):
        raise ActionURLInvalid("signature mismatch")

    payload = {k: v for k, v in query_params.items() if k not in ("sig", "exp")}
    return VerifiedAction(payload=payload, expires_at=expires_at)
