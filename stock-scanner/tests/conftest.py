import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SCANNER_DATA_PROVIDER"] = "synthetic"
os.environ["SCANNER_ENV"] = "development"
os.environ["SCANNER_API_KEYS"] = ""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core import config, security
    from app.data import provider

    monkeypatch.setenv("SCANNER_DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("SCANNER_SCAN_RATE_LIMIT", "1000")
    monkeypatch.setenv("SCANNER_RATE_LIMIT", "10000")
    config.get_settings.cache_clear()
    provider.set_provider(None)
    security.limiter.reset()
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
    config.get_settings.cache_clear()


@pytest.fixture()
def secure_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core import config, security
    from app.data import provider

    monkeypatch.setenv("SCANNER_DATABASE_PATH", str(tmp_path / "s.db"))
    monkeypatch.setenv("SCANNER_API_KEYS", "k" * 40)
    monkeypatch.setenv("SCANNER_SCAN_RATE_LIMIT", "3")
    config.get_settings.cache_clear()
    provider.set_provider(None)
    security.limiter.reset()
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
    config.get_settings.cache_clear()
