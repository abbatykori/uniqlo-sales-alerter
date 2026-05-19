"""Saved-filter validation and conflict cases."""

from __future__ import annotations


def _payload(**overrides) -> dict:
    base = {
        "name": "Default",
        "gender": ["men"],
        "min_discount": 40.0,
        "sizes_clothing": [],
        "sizes_pants": [],
        "sizes_shoes": [],
        "one_size_match": False,
        "availability_mode": "both",
        "ignored_keywords": [],
        "enabled": True,
        "snooze_until": None,
    }
    base.update(overrides)
    return base


def test_invalid_gender_rejected(client):
    resp = client.post("/api/v1/filters", json=_payload(gender=["xenomorph"]))
    assert resp.status_code == 422
    assert "gender" in resp.text.lower()


def test_negative_min_discount_rejected(client):
    resp = client.post("/api/v1/filters", json=_payload(min_discount=-5))
    assert resp.status_code == 422


def test_min_discount_over_100_rejected(client):
    resp = client.post("/api/v1/filters", json=_payload(min_discount=150))
    assert resp.status_code == 422


def test_invalid_availability_mode_rejected(client):
    resp = client.post("/api/v1/filters", json=_payload(availability_mode="storefront"))
    assert resp.status_code == 422


def test_duplicate_name_rejected(client):
    first = client.post("/api/v1/filters", json=_payload(name="Unique"))
    assert first.status_code == 201
    second = client.post("/api/v1/filters", json=_payload(name="Unique"))
    assert second.status_code == 409


def test_blank_name_rejected(client):
    resp = client.post("/api/v1/filters", json=_payload(name="   "))
    assert resp.status_code == 422
