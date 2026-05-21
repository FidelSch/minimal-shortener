import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

import main


class DummyRedis:
    def __init__(self, values=None, set_results=None):
        self.values = values or {}
        self.set_results = list(set_results or [])
        self.set_calls = []
        self.get_calls = []

    async def set(self, key, value, nx=False):
        self.set_calls.append((key, value, nx))
        if self.set_results:
            return self.set_results.pop(0)
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key):
        self.get_calls.append(key)
        return self.values.get(key)

    async def ping(self):
        return True

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_generate_code_length_and_charset():
    code = main._generate_code()
    assert len(code) == 6
    assert code.isalnum()


@pytest.mark.asyncio
async def test_shorten_url_creates_new_code(monkeypatch):
    dummy = DummyRedis()
    monkeypatch.setattr(main, "_redis", dummy)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/shorten", json={"url": "https://example.com"})

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["short_code"]
    assert data["short_url"] == f"http://test/{data['short_code']}"
    assert dummy.values[f"url:{data['short_code']}"] == "https://example.com/"


@pytest.mark.asyncio
async def test_shorten_url_retries_on_collision(monkeypatch):
    dummy = DummyRedis(set_results=[False, True])
    monkeypatch.setattr(main, "_redis", dummy)

    codes = iter(["abc123", "def456"])
    monkeypatch.setattr(main, "_generate_code", lambda length=6: next(codes))

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/shorten", json={"url": "https://example.com"})

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["short_code"] == "def456"
    assert dummy.set_calls[0][0] == "url:abc123"
    assert dummy.set_calls[1][0] == "url:def456"


@pytest.mark.asyncio
async def test_shorten_url_fails_after_ten_collisions(monkeypatch):
    dummy = DummyRedis(set_results=[False] * 11)
    monkeypatch.setattr(main, "_redis", dummy)
    monkeypatch.setattr(main, "_generate_code", lambda length=6: "collision")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/shorten", json={"url": "https://example.com"})

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "Could not generate a unique code"
    assert len(dummy.set_calls) == 10


@pytest.mark.asyncio
async def test_redirect_to_original_url(monkeypatch):
    dummy = DummyRedis(values={"url:xyz789": "https://example.com"})
    monkeypatch.setattr(main, "_redis", dummy)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/xyz789", follow_redirects=False)

    assert response.status_code == status.HTTP_302_FOUND
    assert response.headers["location"] == "https://example.com"


@pytest.mark.asyncio
async def test_redirect_returns_404_for_missing_code(monkeypatch):
    dummy = DummyRedis()
    monkeypatch.setattr(main, "_redis", dummy)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/missing", follow_redirects=False)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Short code not found"


@pytest.mark.asyncio
async def test_health_endpoint_ok(monkeypatch):
    dummy = DummyRedis()
    monkeypatch.setattr(main, "_redis", dummy)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "ok"
    assert response.json()["redis"] == "connected"


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus(monkeypatch):
    dummy = DummyRedis()
    monkeypatch.setattr(main, "_redis", dummy)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == status.HTTP_200_OK
    assert "http_requests_total" in response.text
