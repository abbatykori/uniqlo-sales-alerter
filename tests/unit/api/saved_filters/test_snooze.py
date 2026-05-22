"""Snooze + resume on /api/v1/filters/{id}/{snooze,resume} and /filters/{id}."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _post(client, path: str, data: dict | None = None):
    return client.post(path, data=data or {})


def _create_filter(client, name: str = "Tester") -> int:
    resp = client.post(
        "/api/v1/filters",
        json={"name": name, "gender": ["men"], "min_discount": 40},
    )
    return resp.json()["id"]


# ---------------- REST ----------------


def test_rest_snooze_1d_sets_timestamp(client):
    fid = _create_filter(client)
    r = client.post(f"/api/v1/filters/{fid}/snooze?duration=1d")
    assert r.status_code == 200
    until = r.json()["snooze_until"]
    assert until is not None
    # SQLite stores naive UTC; compare against UTC-naive now()
    naive_utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = datetime.fromisoformat(until) - naive_utc_now
    assert timedelta(hours=23) <= delta <= timedelta(hours=25)


def test_rest_snooze_forever_uses_9999_sentinel(client):
    fid = _create_filter(client)
    r = client.post(f"/api/v1/filters/{fid}/snooze?duration=forever")
    assert r.status_code == 200
    assert "9999" in r.json()["snooze_until"]


def test_rest_resume_clears_timestamp(client):
    fid = _create_filter(client)
    client.post(f"/api/v1/filters/{fid}/snooze?duration=7d")
    r = client.post(f"/api/v1/filters/{fid}/resume")
    assert r.status_code == 200
    assert r.json()["snooze_until"] is None


def test_rest_snooze_invalid_duration_returns_400(client):
    fid = _create_filter(client)
    r = client.post(f"/api/v1/filters/{fid}/snooze?duration=10y")
    assert r.status_code == 400


def test_rest_snooze_unknown_filter_returns_404(client):
    r = client.post("/api/v1/filters/9999/snooze?duration=1d")
    assert r.status_code == 404


def test_rest_resume_unknown_filter_returns_404(client):
    r = client.post("/api/v1/filters/9999/resume")
    assert r.status_code == 404


# ---------------- HTMX UI ----------------


def test_ui_snooze_popover_renders_four_durations(client):
    fid = _create_filter(client)
    r = client.get(f"/filters/{fid}/snooze")
    assert r.status_code == 200
    for d in ("1d", "7d", "30d", "forever"):
        assert f'"duration": "{d}"' in r.text


def test_ui_snooze_post_returns_muted_row(client):
    fid = _create_filter(client)
    r = client.post(f"/filters/{fid}/snooze", data={"duration": "1d"})
    assert r.status_code == 200
    assert "Snoozed until" in r.text
    assert "opacity:0.55" in r.text


def test_ui_snooze_forever_renders_indefinite_label(client):
    fid = _create_filter(client)
    r = client.post(f"/filters/{fid}/snooze", data={"duration": "forever"})
    assert r.status_code == 200
    assert "Snoozed indefinitely" in r.text


def test_ui_resume_clears_snooze_state(client):
    fid = _create_filter(client)
    client.post(f"/filters/{fid}/snooze", data={"duration": "7d"})
    r = client.post(f"/filters/{fid}/resume")
    assert r.status_code == 200
    assert "Snoozed" not in r.text  # the snoozed sub-line is gone
    assert "Resume now" not in r.text  # button text reverts to Snooze


def test_ui_unsnoozed_row_shows_snooze_button(client):
    _create_filter(client)
    r = client.get("/filters")
    assert r.status_code == 200
    # The Snooze button text has surrounding whitespace from template indentation.
    assert "hx-get=\"/filters/" in r.text
    assert "Snooze\n" in r.text or "Snooze " in r.text


def test_snooze_then_resume_is_idempotent(client):
    fid = _create_filter(client)
    client.post(f"/filters/{fid}/snooze", data={"duration": "7d"})
    # Re-applying with a different duration extends.
    r = client.post(f"/filters/{fid}/snooze", data={"duration": "30d"})
    assert r.status_code == 200
    # Resume twice — second call still 200 (no error even though already resumed)
    assert client.post(f"/filters/{fid}/resume").status_code == 200
    assert client.post(f"/filters/{fid}/resume").status_code == 200
