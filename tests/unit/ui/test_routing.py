"""Routing — root-mounted UI plus 308 redirects from the legacy ``/ui/*`` paths."""

from __future__ import annotations


def test_root_serves_deals_view(client) -> None:
    """GET / renders the deals page (not the legacy /settings)."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Deals" in response.text


def test_legacy_ui_prefix_redirects_to_root(client) -> None:
    """v2.0 bookmarks on /ui/* keep working via a 308 redirect."""
    response = client.get("/ui/filters", follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == "/filters"


def test_legacy_ui_root_redirects_to_root(client) -> None:
    """The bare /ui path redirects to /."""
    response = client.get("/ui/", follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == "/"


def test_legacy_ui_redirect_preserves_nested_paths(client) -> None:
    """Multi-segment paths under /ui/ rewrite verbatim under /."""
    response = client.get("/ui/help/tutorials", follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == "/help/tutorials"


def test_breadcrumb_renders_on_filters_page(client) -> None:
    """Page header partial puts a breadcrumb nav on /filters."""
    response = client.get("/filters")
    assert response.status_code == 200
    assert 'aria-label="Breadcrumb"' in response.text
    assert "Filters" in response.text
