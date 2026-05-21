"""ALERTER_SECRET resolution: env var, file fallback, auto-generation."""

from __future__ import annotations

import os
import re
import stat

from uniqlo_sales_alerter.secret import load_or_create_secret


def test_env_var_wins_over_file(tmp_path, monkeypatch):
    secret_file = tmp_path / ".secret"
    secret_file.write_text("from-disk\n")
    monkeypatch.setenv("ALERTER_SECRET", "from-env")
    assert load_or_create_secret(secret_file) == "from-env"


def test_reads_existing_file_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERTER_SECRET", raising=False)
    secret_file = tmp_path / ".secret"
    secret_file.write_text("persisted-value\n")
    assert load_or_create_secret(secret_file) == "persisted-value"


def test_generates_and_persists_when_neither_present(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERTER_SECRET", raising=False)
    secret_file = tmp_path / "subdir" / ".secret"
    value = load_or_create_secret(secret_file)
    assert re.fullmatch(r"[0-9a-f]{64}", value), f"expected 64-char hex, got {value!r}"
    assert secret_file.exists()
    assert secret_file.read_text(encoding="utf-8") == value


def test_generated_file_has_0600_permission(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERTER_SECRET", raising=False)
    secret_file = tmp_path / ".secret"
    load_or_create_secret(secret_file)
    mode = stat.S_IMODE(os.stat(secret_file).st_mode)
    assert mode == 0o600


def test_idempotent_across_calls(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERTER_SECRET", raising=False)
    secret_file = tmp_path / ".secret"
    first = load_or_create_secret(secret_file)
    second = load_or_create_secret(secret_file)
    assert first == second


def test_empty_env_var_is_treated_as_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERTER_SECRET", "   ")
    secret_file = tmp_path / ".secret"
    secret_file.write_text("from-disk\n")
    assert load_or_create_secret(secret_file) == "from-disk"


def test_empty_file_triggers_regeneration(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERTER_SECRET", raising=False)
    secret_file = tmp_path / ".secret"
    secret_file.write_text("")
    value = load_or_create_secret(secret_file)
    assert re.fullmatch(r"[0-9a-f]{64}", value)


def test_default_path_resolution(monkeypatch, tmp_path):
    """The ALERTER_SECRET_PATH env var overrides the default path."""
    monkeypatch.delenv("ALERTER_SECRET", raising=False)
    custom = tmp_path / "custom.secret"
    monkeypatch.setenv("ALERTER_SECRET_PATH", str(custom))
    value = load_or_create_secret()
    assert custom.exists()
    assert custom.read_text(encoding="utf-8") == value
