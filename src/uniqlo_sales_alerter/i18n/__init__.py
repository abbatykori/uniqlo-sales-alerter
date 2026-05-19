"""i18n bootstrap.

Provides a ``gettext`` translator that loads compiled ``.mo`` catalogues from
``locale/<lang>/LC_MESSAGES/messages.mo``. Falls back to identity translation
(return the source string) when a catalogue is missing.

The module exposes ``_`` bound to the English catalogue for convenient
top-level imports. Per-request translator selection is the responsibility of
the FastAPI dependency that builds the response context (added in a later
phase when the UI grows real strings).
"""

from __future__ import annotations

import gettext
from pathlib import Path

LOCALE_DIR: Path = Path(__file__).parent / "locale"
DOMAIN: str = "messages"


def get_translator(lang: str = "en") -> gettext.NullTranslations:
    """Return a ``gettext`` translator for *lang* with identity fallback."""
    return gettext.translation(
        DOMAIN,
        localedir=LOCALE_DIR,
        languages=[lang],
        fallback=True,
    )


_ = get_translator("en").gettext

__all__ = ["DOMAIN", "LOCALE_DIR", "_", "get_translator"]
