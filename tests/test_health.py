from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_ok():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["db"] == "DATABASE_URL is not set"


def test_redact_hides_credentials():
    from app.main import _redact

    out = _redact("bad dsn postgresql://user:s3cret@host/db and password=s3cret")
    assert "s3cret" not in out
