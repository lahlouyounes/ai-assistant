import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def tmp_dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "memory_db", str(tmp_path / "m.db"))
    monkeypatch.setattr(settings, "notes_db", str(tmp_path / "n.db"))
    monkeypatch.setattr(settings, "http_allowed_hosts", [])
