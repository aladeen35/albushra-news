import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_TOKEN"] = "test-token"
os.environ["ADMIN_USERNAME"] = "editor"
os.environ["ADMIN_PASSWORD"] = "correct horse"
for key in ("GNEWS_API_KEY", "WORLDNEWS_API_KEY", "NEWSAPI_KEY", "DTM_SUBSCRIPTION_KEY",
            "ACLED_USERNAME", "ACLED_PASSWORD"):
    os.environ.pop(key, None)
os.environ["SCHEDULER_ENABLED"] = "false"  # tests must never reach the network

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture
def session():
    db.configure("sqlite:///:memory:")
    db.init_db()
    s = db.SessionLocal()
    seed(s)
    yield s
    s.close()
    db.Base.metadata.drop_all(db.engine)


@pytest.fixture
def client(session):
    from app.main import app, limiter
    limiter.hits.clear()
    with TestClient(app) as c:
        yield c


ADMIN = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Real transports fail at once; tests that need HTTP pass a MockTransport."""
    import httpx

    def refuse(self, request):
        raise httpx.ConnectError("network disabled in tests", request=request)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr("app.providers.base.time.sleep", lambda s: None)


@pytest.fixture(autouse=True)
def _ocha_offline(monkeypatch):
    """The OCHA reader needs no key, so it would run in every metrics test: keep it offline."""
    import httpx
    from app.providers import ocha
    from app.providers.base import HttpClient
    monkeypatch.setattr(ocha, "HttpClient", lambda retries=1: HttpClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(503)), retries=0, backoff=0))
    ocha.reset_cache()
