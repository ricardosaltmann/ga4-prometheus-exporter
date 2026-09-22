"""Integration tests for Realtime Collector with mocked GA4 API responses."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from ga4_exporter.collectors.realtime import RealtimeCollector
from ga4_exporter.config import AppConfig, PropertyConfig
from ga4_exporter.metrics.cache import MetricsCache
from ga4_exporter.metrics.internal import COLLECTOR_UP


def test_realtime_collector_successful_response():
    """Test realtime collector parsing response with active users and quota."""
    config = AppConfig(
        properties=[PropertyConfig(name="portal", property_id="123456789")],
        quota={"enabled": True},
    )
    cache = MetricsCache()
    mock_client = MagicMock()

    # Mock response
    mock_resp = SimpleNamespace(
        rows=[
            SimpleNamespace(
                dimension_values=[],
                metric_values=[SimpleNamespace(value="85")],
            )
        ],
        property_quota=SimpleNamespace(
            tokens_per_hour=SimpleNamespace(consumed=15, remaining=39985),
            tokens_per_day=SimpleNamespace(consumed=200, remaining=49800),
            concurrent_requests=SimpleNamespace(consumed=1, remaining=9),
        ),
    )
    mock_client.run_realtime_report.return_value = mock_resp

    collector = RealtimeCollector(
        config=config,
        property_config=config.properties[0],
        client=mock_client,
        cache=cache,
    )

    collector.run()

    # Verify telemetry
    assert COLLECTOR_UP.labels(property="portal", collector="realtime")._value.get() == 1

    # Verify cached samples
    samples = {s.name: s.value for s in cache.get_all_samples()}
    assert samples.get("ga4_realtime_active_users") == 85.0
    assert samples.get("ga4_api_quota_tokens_per_hour_remaining") == 39985.0


def test_realtime_collector_empty_rows_yields_zero():
    """Test that empty response rows results in 0 value with success status."""
    config = AppConfig(
        properties=[PropertyConfig(name="portal", property_id="123456789")],
    )
    cache = MetricsCache()
    mock_client = MagicMock()

    mock_resp = SimpleNamespace(rows=[], property_quota=None)
    mock_client.run_realtime_report.return_value = mock_resp

    collector = RealtimeCollector(
        config=config,
        property_config=config.properties[0],
        client=mock_client,
        cache=cache,
    )

    collector.run()

    assert COLLECTOR_UP.labels(property="portal", collector="realtime")._value.get() == 1
    samples = {s.name: s.value for s in cache.get_all_samples()}
    assert samples.get("ga4_realtime_active_users") == 0.0
