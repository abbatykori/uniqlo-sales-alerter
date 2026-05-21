"""HMAC secret loader.

The HMAC-signed notification action URLs (step 11) need a stable secret
shared between the signer (template renderer) and the verifier (action
handler). Resolution order:

1. ``ALERTER_SECRET`` environment variable, if set and non-empty.
2. Contents of ``ALERTER_SECRET_PATH`` (default ``/app/data/.secret``)
   if the file exists.
3. Generate 32 random bytes, hex-encode, write to the path with mode
   ``0600``, and return.

The auto-generated path defaults to ``/app/data/.secret`` (inside the
data volume), so the secret survives container restarts when the
volume is mounted. The path is overridable via the
``ALERTER_SECRET_PATH`` env var for local development.

This module is intentionally tiny so it can be safely imported during
the FastAPI lifespan before any heavy dependencies load.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_SECRET_PATH = "/app/data/.secret"
_SECRET_BYTES = 32


def _resolve_secret_path() -> Path:
    return Path(os.environ.get("ALERTER_SECRET_PATH", _DEFAULT_SECRET_PATH))


def load_or_create_secret(path: Path | None = None) -> str:
    """Return the HMAC secret, generating + persisting one on first run.

    Env var ``ALERTER_SECRET`` wins if set. Otherwise reads the file at
    *path* (default ``/app/data/.secret`` or ``ALERTER_SECRET_PATH``),
    or generates a fresh secret and writes it to that path.
    """
    env_value = os.environ.get("ALERTER_SECRET", "").strip()
    if env_value:
        logger.debug("ALERTER_SECRET loaded from environment")
        return env_value

    target = path if path is not None else _resolve_secret_path()
    if target.exists():
        existing = target.read_text(encoding="utf-8").strip()
        if existing:
            logger.debug("ALERTER_SECRET loaded from %s", target)
            return existing
        logger.warning("Secret file %s exists but is empty; regenerating", target)

    target.parent.mkdir(parents=True, exist_ok=True)
    new_secret = secrets.token_hex(_SECRET_BYTES)
    target.write_text(new_secret, encoding="utf-8")
    target.chmod(0o600)
    logger.info("Generated new ALERTER_SECRET at %s", target)
    return new_secret
