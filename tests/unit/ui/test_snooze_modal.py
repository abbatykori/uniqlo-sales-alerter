"""Snooze modal — replaces the v2.0 inline popover that broke the filter table."""

from __future__ import annotations


def _create_filter(client, name: str = "Tester") -> int:
    # v2.1 derives ``enabled`` from data presence: a filter needs at least one
    # gender AND at least one size category to count as active. Pass both so
    # the status pill renders as "Active" instead of "Disabled".
    resp = client.post(
        "/api/v1/filters",
        json={
            "name": name,
            "gender": ["men"],
            "sizes_clothing": ["M"],
            "min_discount": 40,
        },
    )
    return resp.json()["id"]


def test_modal_container_renders_in_base(client) -> None:
    """The global modal container is present on every page."""
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="modal-content"' in response.text


def test_snooze_endpoint_returns_modal_markup(client) -> None:
    """GET /filters/{id}/snooze returns the modal partial (not the inline popover)."""
    filter_id = _create_filter(client)
    response = client.get(f"/filters/{filter_id}/snooze")
    assert response.status_code == 200
    # Modal must have an overlay backdrop + dialog role.
    assert 'role="dialog"' in response.text
    assert 'aria-modal="true"' in response.text
    assert "fixed inset-0" in response.text


def test_snooze_modal_lists_four_durations(client) -> None:
    """The modal exposes 1d / 7d / 30d / Forever buttons."""
    filter_id = _create_filter(client)
    response = client.get(f"/filters/{filter_id}/snooze")
    for duration in ("1d", "7d", "30d", "forever"):
        assert f'"duration": "{duration}"' in response.text


def test_snooze_modal_closes_after_request(client) -> None:
    """Each duration button clears #modal-content via hx-on::after-request."""
    filter_id = _create_filter(client)
    response = client.get(f"/filters/{filter_id}/snooze")
    assert "hx-on::after-request" in response.text
    assert "modal-content" in response.text


def test_snooze_button_targets_modal_container(client) -> None:
    """The Snooze action button on a filter row swaps into the global modal."""
    _create_filter(client)
    response = client.get("/filters")
    assert 'hx-target="#modal-content"' in response.text


def test_filter_row_has_status_column(client) -> None:
    """v2.1 surfaces snooze state as a coloured dot + label in its own column."""
    _create_filter(client)
    response = client.get("/filters")
    # Active filter renders the green dot + "Active" label.
    assert "Active" in response.text
    assert "bg-status-success" in response.text


def test_snoozed_row_renders_amber_status_pill(client) -> None:
    """Snoozed filters render an amber 'Snoozed' status."""
    filter_id = _create_filter(client)
    response = client.post(f"/filters/{filter_id}/snooze", data={"duration": "7d"})
    assert "Snoozed" in response.text
    assert "bg-status-warning" in response.text


def test_forever_snooze_renders_red_status_pill(client) -> None:
    """The year-9999 sentinel ('forever' snooze) gets the red pill."""
    filter_id = _create_filter(client)
    response = client.post(f"/filters/{filter_id}/snooze", data={"duration": "forever"})
    assert "Forever snoozed" in response.text
    assert "bg-status-error" in response.text
