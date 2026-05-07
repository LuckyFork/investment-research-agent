import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture(autouse=True)
def mock_infra_connections():
    """Mock all infrastructure connections so unit tests don't need real services."""
    with (
        # Patch at the import site (where health.py imported them)
        patch("app.api.v1.health.check_db_connection", new_callable=AsyncMock, return_value=True),
        patch("app.api.v1.health.check_redis_connection", new_callable=AsyncMock, return_value=True),
        patch("app.api.v1.health.check_qdrant_connection", new_callable=AsyncMock, return_value=True),
        # Patch lifespan hooks
        patch("app.main.ensure_collections", new_callable=AsyncMock),
        patch("app.main.close_db", new_callable=AsyncMock),
        patch("app.main.close_redis", new_callable=AsyncMock),
        patch("app.main.close_qdrant", new_callable=AsyncMock),
    ):
        yield
