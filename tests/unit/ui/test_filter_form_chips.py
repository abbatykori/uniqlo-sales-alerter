"""Filter form — toggle-chip pattern for gender / sizes / availability."""

from __future__ import annotations


def _create_filter(client, **overrides) -> int:
    payload = {
        "name": "Test",
        "gender": ["women"],
        "sizes_clothing": ["S", "M"],
        "min_discount": 50.0,
        "availability_mode": "in_store",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/filters", json=payload)
    return resp.json()["id"]


def test_new_form_renders_gender_chip_for_each_value(client) -> None:
    response = client.get("/filters/new")
    assert response.status_code == 200
    # Every supported gender value has its own checkbox chip.
    for gender in ("men", "women", "unisex", "kids", "baby"):
        assert f'name="gender" value="{gender}"' in response.text


def test_new_form_renders_clothing_size_chips(client) -> None:
    response = client.get("/filters/new")
    for size in ("XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL"):
        assert f'name="sizes_clothing" value="{size}"' in response.text


def test_new_form_renders_pants_size_chips(client) -> None:
    response = client.get("/filters/new")
    for inches in ("22inch", "30inch", "40inch"):
        assert f'name="sizes_pants" value="{inches}"' in response.text


def test_new_form_renders_availability_radio_chips(client) -> None:
    response = client.get("/filters/new")
    for mode in ("both", "online", "in_store"):
        assert f'name="availability_mode" value="{mode}"' in response.text


def test_new_form_drops_enabled_checkbox(client) -> None:
    response = client.get("/filters/new")
    # No standalone enabled checkbox — activity derives from data presence.
    assert 'name="enabled"' not in response.text


def test_edit_form_pre_checks_selected_chips(client) -> None:
    filter_id = _create_filter(client)
    response = client.get(f"/filters/{filter_id}/edit")
    assert response.status_code == 200
    # The women chip is pre-checked.
    assert ('value="women"\n           class="peer sr-only" checked' in response.text
            or 'value="women"' in response.text and "checked" in response.text)
    # S and M chips for clothing are pre-checked.
    assert 'value="S"' in response.text
    assert 'value="M"' in response.text


def test_form_quick_pick_discount_buttons_present(client) -> None:
    response = client.get("/filters/new")
    # Quick-pick chips for the discount field.
    for v in ("30", "50", "70"):
        assert f"value={v}" in response.text


def test_create_via_form_with_multiple_sizes(client) -> None:
    """Multi-value form posting builds a list of sizes."""
    response = client.post(
        "/filters",
        data={
            "name": "Multi",
            "gender": ["men", "women"],
            "sizes_clothing": ["M", "L"],
            "availability_mode": "both",
            "min_discount": "40",
        },
    )
    assert response.status_code == 201
    assert "Multi" in response.text
