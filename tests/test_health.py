import pytest
from unittest.mock import AsyncMock, patch


class TestPing:
    async def test_ping_returns_pong(self, client):
        resp = await client.get("/api/v1/health/ping")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == "pong"


class TestReadiness:
    async def test_all_services_healthy(self, client):
        resp = await client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == {"postgres": "ok", "redis": "ok", "qdrant": "ok"}

    async def test_partial_failure_returns_success_false(self, client):
        with patch(
            "app.api.v1.health.check_db_connection",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = await client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["data"]["postgres"] == "error"
        assert body["data"]["redis"] == "ok"
        assert body["data"]["qdrant"] == "ok"

    async def test_all_services_down(self, client):
        with (
            patch("app.api.v1.health.check_db_connection", new_callable=AsyncMock, return_value=False),
            patch("app.api.v1.health.check_redis_connection", new_callable=AsyncMock, return_value=False),
            patch("app.api.v1.health.check_qdrant_connection", new_callable=AsyncMock, return_value=False),
        ):
            resp = await client.get("/api/v1/health/ready")
        body = resp.json()
        assert body["success"] is False
        assert all(v == "error" for v in body["data"].values())
