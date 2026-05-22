"""Base shell template + static mount + token codegen."""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_static_tokens_css_is_served(client):
    r = client.get("/static/tokens.css")
    assert r.status_code == 200
    # Generated header marker
    assert "Auto-generated from design/tokens/tokens.json" in r.text
    # Spot-check a known variable
    assert "--color-accent-primary" in r.text


def test_base_shell_includes_tailwind_cdn(client):
    """The new base.html should pull Tailwind from a CDN until we wire the CLI."""
    r = client.get("/filters")
    assert r.status_code == 200
    assert "cdn.tailwindcss.com" in r.text
    assert '<link rel="stylesheet" href="/static/tokens.css"' in r.text


def test_base_shell_has_desktop_sidebar_and_mobile_tab_bar(client):
    r = client.get("/filters")
    assert r.status_code == 200
    # Sidebar (hidden on mobile, flex on desktop)
    assert "hidden md:flex" in r.text
    # Bottom tab bar (visible on mobile, hidden on desktop)
    assert "md:hidden" in r.text
    # Five tabs in the bar
    for label in ("Deals", "Filters", "Inbox", "Insights", "More"):
        assert label in r.text


def test_token_codegen_writes_all_token_variables() -> None:
    """Run build-tokens.py and verify the output."""
    root = Path(__file__).resolve().parents[3]
    script = root / "design" / "scripts" / "build-tokens.py"
    out = root / "src" / "uniqlo_sales_alerter" / "ui" / "static" / "tokens.css"
    result = subprocess.run(
        ["python3", str(script)], capture_output=True, text=True, cwd=root,
    )
    assert result.returncode == 0, result.stderr
    content = out.read_text(encoding="utf-8")
    # Spot-check a representative set
    for var in (
        "--color-surface-canvas",
        "--color-text-primary",
        "--color-accent-primary",
        "--color-status-error",
        "--radius-md",
    ):
        assert var in content
