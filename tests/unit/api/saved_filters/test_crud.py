"""Saved-filter REST CRUD end-to-end."""

from __future__ import annotations


def _make_payload(**overrides) -> dict:
    base = {
        "name": "Test filter",
        "gender": ["men"],
        "min_discount": 40.0,
        "sizes_clothing": ["M", "L"],
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


def test_list_empty(client):
    resp = client.get("/api/v1/filters")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_and_read(client):
    create_resp = client.post("/api/v1/filters", json=_make_payload(name="Me tops"))
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["id"] >= 1
    assert data["name"] == "Me tops"
    assert data["gender"] == ["men"]

    get_resp = client.get(f"/api/v1/filters/{data['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Me tops"


def test_list_after_create(client):
    client.post("/api/v1/filters", json=_make_payload(name="A"))
    client.post("/api/v1/filters", json=_make_payload(name="B"))
    resp = client.get("/api/v1/filters")
    assert resp.status_code == 200
    names = [row["name"] for row in resp.json()]
    assert names == ["A", "B"]


def test_update(client):
    create = client.post("/api/v1/filters", json=_make_payload(name="orig"))
    filter_id = create.json()["id"]

    updated_payload = _make_payload(name="renamed", min_discount=70.0)
    update_resp = client.put(f"/api/v1/filters/{filter_id}", json=updated_payload)
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "renamed"
    assert update_resp.json()["min_discount"] == 70.0


def test_delete(client):
    create = client.post("/api/v1/filters", json=_make_payload(name="to-delete"))
    filter_id = create.json()["id"]
    delete_resp = client.delete(f"/api/v1/filters/{filter_id}")
    assert delete_resp.status_code == 204

    follow_up = client.get(f"/api/v1/filters/{filter_id}")
    assert follow_up.status_code == 404


def test_duplicate(client):
    create = client.post("/api/v1/filters", json=_make_payload(name="Source"))
    filter_id = create.json()["id"]
    dup_resp = client.post(f"/api/v1/filters/{filter_id}/duplicate")
    assert dup_resp.status_code == 201
    assert dup_resp.json()["name"] == "Source (copy)"
    assert dup_resp.json()["id"] != filter_id


def test_update_missing(client):
    resp = client.put("/api/v1/filters/9999", json=_make_payload())
    assert resp.status_code == 404


def test_delete_missing(client):
    resp = client.delete("/api/v1/filters/9999")
    assert resp.status_code == 404
