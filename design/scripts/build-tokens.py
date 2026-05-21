#!/usr/bin/env python3
"""Codegen ``tokens.css`` from ``tokens.json``.

Walks the W3C-DTFM-format token tree and emits CSS custom properties
keyed by the dot-joined path with hyphens (``color.text.primary`` →
``--color-text-primary``). Idempotent — run after every token change.

Output: ``src/uniqlo_sales_alerter/ui/static/tokens.css``.
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "design" / "tokens" / "tokens.json"
_OUT = _ROOT / "src" / "uniqlo_sales_alerter" / "ui" / "static" / "tokens.css"


def _walk(prefix: list[str], node: dict, out: list[tuple[str, str]]) -> None:
    if isinstance(node, dict) and "$value" in node:
        var_name = "--" + "-".join(prefix)
        out.append((var_name, str(node["$value"])))
        return
    if not isinstance(node, dict):
        return
    for key, child in node.items():
        if key.startswith("$"):
            continue
        _walk(prefix + [key], child, out)


def main() -> None:
    data = json.loads(_SRC.read_text(encoding="utf-8"))
    vars_list: list[tuple[str, str]] = []
    for key, child in data.items():
        if key.startswith("$"):
            continue
        _walk([key], child, vars_list)

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "/* Auto-generated from design/tokens/tokens.json — do not edit. */",
        "/* Run design/scripts/build-tokens.py after changing tokens.json. */",
        ":root {",
    ]
    for name, value in vars_list:
        lines.append(f"  {name}: {value};")
    lines.append("}")
    lines.append("")
    _OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(vars_list)} CSS variables to {_OUT}")


if __name__ == "__main__":
    main()
