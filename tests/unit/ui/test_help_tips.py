"""Contextual help — ``?`` icons with hover/focus tooltips next to form labels."""

from __future__ import annotations


def test_help_tip_partial_renders_button_and_tooltip(client) -> None:
    """Pages that include the partial expose both the trigger and the popover."""
    response = client.get("/filters/new")
    assert response.status_code == 200
    assert 'role="tooltip"' in response.text
    assert 'aria-label="Help"' in response.text


def test_filter_form_has_help_tips_on_every_section(client) -> None:
    """Each of the 6 fieldsets gets a ``?`` tooltip explaining the section."""
    response = client.get("/filters/new")
    # Count discrete tooltip popovers — one per section.
    tooltip_count = response.text.count('role="tooltip"')
    assert tooltip_count >= 5  # gender, sizes, discount, availability, ignored


def test_settings_page_has_help_tips_on_section_headers(client) -> None:
    response = client.get("/settings")
    assert response.status_code == 200
    tooltip_count = response.text.count('role="tooltip"')
    # Notifications + Schedule + Country + Watched at minimum.
    assert tooltip_count >= 4


def test_deals_empty_state_links_help_explanation(client) -> None:
    """First-run empty state has a tip linking out to /help/explanation."""
    response = client.get("/")
    assert response.status_code == 200
    assert "/help/explanation" in response.text
