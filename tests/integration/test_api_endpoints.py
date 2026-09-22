"""Integration tests for HTTP endpoints (/metrics, /health, /ready, /status)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from prometheus_client import CollectorRegistry

from ga4_exporter.api.app import create_app
from ga4_exporter.config import AppConfig, PropertyConfig
from ga4_exporter.metrics.cache import MetricsCache
from ga4_exporter.metrics.ga4 import MetricSample


@pytest.fixture
def test_app():
    """Create a configured test application with mocked client."""
    config = AppConfig(
        properties=[PropertyConfig(name="portal", property_id="123456789")],
    )
    cache = MetricsCache()
    # Add dummy sample
    cache.update_success(
        "portal",
        "realtime",
        [MetricSample(name="ga4_realtime_active_users", labels={"property": "portal"}, value=74.0)],
    )

    mock_client = MagicMock()
    mock_scheduler = MagicMock()
    mock_scheduler.is_ready = True
    mock_scheduler.start = AsyncMock()
    mock_scheduler.stop = AsyncMock()
    test_registry = CollectorRegistry()

    app = create_app(
        config=config,
        client=mock_client,
        cache=cache,
        scheduler=mock_scheduler,
        registry=test_registry,
    )
    return app


@pytest.mark.asyncio
async def test_health_endpoint(test_app):
    """Test /health returns HTTP 200 with status ok."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_endpoint(test_app):
    """Test /ready returns HTTP 200 when scheduler is ready."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        response = await ac.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_status_endpoint_no_secrets(test_app):
    """Test /status returns sanitized summary without private keys or tokens."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        response = await ac.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "portal" in data["properties"]

    # Verify no credentials leaked
    text = response.text
    assert "private_key" not in text
    assert "secret" not in text
    assert "token" not in text


@pytest.mark.asyncio
async def test_metrics_endpoint_format(test_app):
    """Test /metrics produces compliant Prometheus exposition format."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        response = await ac.get("/metrics")
    assert response.status_code == 200
    content = response.text

    # Verify Prometheus headers and metric format
    assert "# HELP" in content
    assert "# TYPE" in content
    assert "ga4_exporter_up" in content
    assert 'ga4_realtime_active_users{property="portal"} 74.0' in content

    # Verify no invalid representations
    assert "NaN" not in content
    assert "Inf" not in content
