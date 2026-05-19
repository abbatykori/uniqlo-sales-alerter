"""Verify the Babel pipeline round-trips: catalogue present, fallback works."""

from __future__ import annotations

from uniqlo_sales_alerter.i18n import DOMAIN, LOCALE_DIR, _, get_translator


def test_en_catalogue_files_present() -> None:
    """The English ``.po`` (and compiled ``.mo``) must ship in the package tree."""
    po_path = LOCALE_DIR / "en" / "LC_MESSAGES" / "messages.po"
    mo_path = LOCALE_DIR / "en" / "LC_MESSAGES" / "messages.mo"
    assert po_path.exists(), f"missing {po_path}"
    assert mo_path.exists(), (
        f"missing {mo_path} — run "
        f"`pybabel compile -d src/uniqlo_sales_alerter/i18n/locale` first"
    )


def test_known_string_translates_identity_in_english() -> None:
    """English catalogue ships the source string unchanged for already-English copy."""
    translator = get_translator("en")
    assert translator.gettext("Healthy") == "Healthy"
    assert translator.gettext("Degraded") == "Degraded"


def test_unknown_locale_falls_back_to_source_string() -> None:
    """A missing catalogue falls back to identity — no exception raised."""
    translator = get_translator("xx")
    assert translator.gettext("Healthy") == "Healthy"


def test_module_level_underscore_is_english_translator() -> None:
    """The package-level ``_`` shortcut returns the English translation."""
    assert _("Healthy") == "Healthy"


def test_domain_constant() -> None:
    assert DOMAIN == "messages"
