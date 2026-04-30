"""Config loading tests — enforce D-09 fail-fast contract."""

import importlib
import sys

import pytest
from pydantic import ValidationError


REQUIRED_ENV = {
    "GEMINI_API_KEY": "test-gemini",
    "LANGFUSE_PUBLIC_KEY": "test-lf-pub",
    "LANGFUSE_SECRET_KEY": "test-lf-secret",
    "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/test",
}


def _reload_config():
    """Force re-import of sva.config so Settings re-reads os.environ.

    Only evict sva.config (not the parent sva package) to avoid breaking
    the submodule namespace for monkeypatch targets in later test files.
    """
    if "sva.config" in sys.modules:
        del sys.modules["sva.config"]
    return importlib.import_module("sva.config")


def test_settings_load_when_all_keys_present(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("LANGFUSE_HOST", "https://custom.langfuse")
    # Prevent .env file fallback from polluting the test.
    monkeypatch.chdir("/tmp")
    mod = _reload_config()
    assert mod.settings.gemini_api_key.get_secret_value() == "test-gemini"
    assert mod.settings.database_url.startswith("postgresql+psycopg://")
    assert mod.settings.langfuse_host == "https://custom.langfuse"


def test_settings_default_langfuse_host(monkeypatch):
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.chdir("/tmp")
    mod = _reload_config()
    assert mod.settings.langfuse_host == "https://cloud.langfuse.com"


def test_settings_raise_on_missing_key(monkeypatch):
    for k in REQUIRED_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir("/tmp")
    # sva.config eager-loads settings on import; missing keys must raise ValidationError.
    if "sva.config" in sys.modules:
        del sys.modules["sva.config"]
    with pytest.raises(ValidationError):
        importlib.import_module("sva.config")
