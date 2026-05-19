"""HTMX UI smoke tests — list page, create form, delete swap."""

from __future__ import annotations


def test_list_empty_renders(client):
    resp = client.get("/ui/filters")
    assert resp.status_code == 200
    assert "No saved filters yet" in resp.text
    assert "Add filter" in resp.text


def test_new_form_renders(client):
    resp = client.get("/ui/filters/new")
    assert resp.status_code == 200
    assert "<form" in resp.text
    assert 'name="name"' in resp.text
    assert 'name="availability_mode"' in resp.text


def test_create_via_form_returns_row_partial(client):
    resp = client.post(
        "/ui/filters",
        data={
            "name": "Me tops",
            "gender": "men",
            "min_discount": "40",
            "sizes_clothing": "M, L",
            "availability_mode": "both",
        },
    )
    assert resp.status_code == 201
    # Row partial returns a single <tr> with the id and name
    assert "<tr id=\"filter-row-" in resp.text
    assert "Me tops" in resp.text


def test_list_after_create_includes_row(client):
    client.post(
        "/ui/filters",
        data={
            "name": "Kid 5y",
            "gender": "kids",
            "min_discount": "50",
            "availability_mode": "online",
        },
    )
    resp = client.get("/ui/filters")
    assert resp.status_code == 200
    assert "<table" in resp.text
    assert "Kid 5y" in resp.text


def test_delete_returns_empty_for_htmx_swap(client):
    create = client.post(
        "/ui/filters",
        data={
            "name": "delete-me",
            "gender": "unisex",
            "min_discount": "30",
            "availability_mode": "both",
        },
    )
    body = create.text
    # Extract the inserted row's id from the partial
    import re

    match = re.search(r'id="filter-row-(\d+)"', body)
    assert match is not None, "expected partial to include filter-row-<id>"
    filter_id = int(match.group(1))

    resp = client.delete(f"/ui/filters/{filter_id}")
    assert resp.status_code == 200
    assert resp.text == ""


def test_create_with_invalid_gender_returns_400(client):
    resp = client.post(
        "/ui/filters",
        data={
            "name": "bad",
            "gender": "xenomorph",
            "min_discount": "30",
            "availability_mode": "both",
        },
    )
    assert resp.status_code == 400
    assert "gender" in resp.text.lower()


def test_edit_form_renders_existing_values(client):
    create = client.post(
        "/ui/filters",
        data={
            "name": "Spouse",
            "gender": "women",
            "min_discount": "60",
            "sizes_clothing": "S",
            "availability_mode": "in_store",
        },
    )
    import re

    filter_id = int(re.search(r'id="filter-row-(\d+)"', create.text).group(1))

    resp = client.get(f"/ui/filters/{filter_id}/edit")
    assert resp.status_code == 200
    assert 'value="Spouse"' in resp.text
    assert 'selected' in resp.text  # availability or gender pre-selected
