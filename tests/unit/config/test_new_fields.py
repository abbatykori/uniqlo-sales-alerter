"""Fork foundation: decoupled ``store_country`` + ``ui_language`` + heatmap threshold.

The three new top-level config keys coexist with upstream's ``uniqlo.country``.
``store_country`` defaults to ``uniqlo.country`` via a model validator so old
YAML files continue to work without edits.
"""

from __future__ import annotations

from uniqlo_sales_alerter.config import AppConfig


def test_defaults_when_only_uniqlo_country_is_set() -> None:
    """A YAML with the upstream shape should populate the new fields automatically."""
    cfg = AppConfig.model_validate(
        {"uniqlo": {"country": "nl/nl"}, "filters": {}, "notifications": {}},
    )
    assert cfg.store_country == "nl/nl"
    assert cfg.ui_language == "en"
    assert cfg.deep_discount_threshold == 50


def test_explicit_store_country_overrides_uniqlo_country() -> None:
    cfg = AppConfig.model_validate(
        {
            "uniqlo": {"country": "de/de"},
            "store_country": "us/en",
            "filters": {},
            "notifications": {},
        }
    )
    assert cfg.store_country == "us/en"
    # uniqlo.country is still the source of truth for the API client until
    # step 8 swaps over.
    assert cfg.uniqlo.country == "de/de"


def test_env_vars_override_defaults(monkeypatch) -> None:
    """STORE_COUNTRY / UI_LANGUAGE / DEEP_DISCOUNT_THRESHOLD must be wired into _ENV_MAP."""
    monkeypatch.setenv("STORE_COUNTRY", "jp/ja")
    monkeypatch.setenv("UI_LANGUAGE", "nl")
    monkeypatch.setenv("DEEP_DISCOUNT_THRESHOLD", "70")

    from uniqlo_sales_alerter.config import _config_from_env

    overrides = _config_from_env()
    assert overrides["store_country"] == "jp/ja"
    assert overrides["ui_language"] == "nl"
    assert overrides["deep_discount_threshold"] == 70


def test_ui_language_independent_of_country() -> None:
    cfg = AppConfig.model_validate(
        {
            "uniqlo": {"country": "nl/nl"},
            "ui_language": "en",
            "filters": {},
            "notifications": {},
        }
    )
    assert cfg.store_country == "nl/nl"
    assert cfg.ui_language == "en"
