"""CountryCapabilities — new fork fields and per-country overrides."""

from __future__ import annotations

import pytest

from uniqlo_sales_alerter.config import AppConfig


def test_default_store_stock_only_reliable_true() -> None:
    cfg = AppConfig.model_validate({"uniqlo": {"country": "nl/nl"}})
    assert cfg.capabilities.store_stock_only_reliable is True


@pytest.mark.parametrize("country", ["ph/en", "th/en", "kr/ko"])
def test_unreliable_countries_opt_out(country: str) -> None:
    cfg = AppConfig.model_validate({"uniqlo": {"country": country}})
    assert cfg.capabilities.store_stock_only_reliable is False


@pytest.mark.parametrize(
    "country",
    ["de/de", "uk/en", "nl/nl", "id/en", "us/en", "sg/en"],
)
def test_other_countries_keep_reliable_default(country: str) -> None:
    cfg = AppConfig.model_validate({"uniqlo": {"country": country}})
    assert cfg.capabilities.store_stock_only_reliable is True
