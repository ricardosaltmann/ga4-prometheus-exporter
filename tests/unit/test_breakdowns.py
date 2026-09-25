"""Unit tests for dimension breakdowns and enriched metrics."""

from unittest.mock import MagicMock

from ga4_exporter.collectors.core import CoreCollector
from ga4_exporter.collectors.realtime import RealtimeCollector
from ga4_exporter.config import (
    AppConfig,
    BreakdownConfig,
    MetricsConfig,
    PropertyConfig,
    RealtimeScreensConfig,
)
from ga4_exporter.metrics.cache import MetricsCache


def test_core_collector_devices_and_channels_enabled():
    """Verify that devices and channels breakdowns are collected when enabled."""
    cache = MetricsCache()
    client = MagicMock()

    # Mock core response
    mock_core = MagicMock()
    mock_core.rows = []
    del mock_core.property_quota

    # Mock devices response
    mock_dev_row = MagicMock()
    mock_dev_row.dimension_values = [MagicMock(value="desktop")]
    mock_dev_row.metric_values = [
        MagicMock(value="100"),
        MagicMock(value="120"),
        MagicMock(value="500"),
    ]
    mock_dev_resp = MagicMock()
    mock_dev_resp.rows = [mock_dev_row]

    # Mock channels response
    mock_tc_row = MagicMock()
    mock_tc_row.dimension_values = [MagicMock(value="Organic Search")]
    mock_tc_row.metric_values = [
        MagicMock(value="250"),
        MagicMock(value="200"),
    ]
    mock_tc_resp = MagicMock()
    mock_tc_resp.rows = [mock_tc_row]

    # client.run_core_report side effects
    client.run_core_report.side_effect = [mock_core, mock_dev_resp, mock_tc_resp]

    cfg = AppConfig(
        properties=[PropertyConfig(name="test_site", property_id="123456")],
        metrics=MetricsConfig(
            devices=BreakdownConfig(enabled=True),
            traffic_channels=BreakdownConfig(enabled=True),
        ),
    )

    collector = CoreCollector(
        config=cfg,
        property_config=cfg.properties[0],
        client=client,
        cache=cache,
    )
    collector.collect()

    samples = cache.get_all_samples()
    sample_names = {s.name for s in samples}
    assert "ga4_device_active_users" in sample_names
    assert "ga4_device_sessions" in sample_names
    assert "ga4_device_screen_page_views" in sample_names
    assert "ga4_traffic_channel_sessions" in sample_names
    assert "ga4_traffic_channel_users" in sample_names


def test_realtime_collector_devices_and_screens_enabled():
    """Verify that realtime devices and screens breakdowns are collected when enabled."""
    cache = MetricsCache()
    client = MagicMock()

    # Mock realtime total
    mock_rt_row = MagicMock()
    mock_rt_row.dimension_values = []
    mock_rt_row.metric_values = [MagicMock(value="42")]
    mock_rt_resp = MagicMock()
    mock_rt_resp.rows = [mock_rt_row]
    del mock_rt_resp.property_quota

    # Mock realtime devices
    mock_dev_row = MagicMock()
    mock_dev_row.dimension_values = [MagicMock(value="mobile")]
    mock_dev_row.metric_values = [MagicMock(value="20")]
    mock_rt_dev_resp = MagicMock()
    mock_rt_dev_resp.rows = [mock_dev_row]

    # Mock realtime screens
    mock_screen_row = MagicMock()
    mock_screen_row.dimension_values = [MagicMock(value="Home Screen")]
    mock_screen_row.metric_values = [MagicMock(value="15")]
    mock_rt_screen_resp = MagicMock()
    mock_rt_screen_resp.rows = [mock_screen_row]

    client.run_realtime_report.side_effect = [mock_rt_resp, mock_rt_dev_resp, mock_rt_screen_resp]

    cfg = AppConfig(
        properties=[PropertyConfig(name="test_site", property_id="123456")],
        metrics=MetricsConfig(
            realtime_devices=BreakdownConfig(enabled=True),
            realtime_screens=RealtimeScreensConfig(enabled=True),
        ),
    )

    collector = RealtimeCollector(
        config=cfg,
        property_config=cfg.properties[0],
        client=client,
        cache=cache,
    )
    collector.collect()

    samples = cache.get_all_samples()
    sample_names = {s.name for s in samples}
    assert "ga4_realtime_active_users" in sample_names
    assert "ga4_realtime_device_active_users" in sample_names
    assert "ga4_realtime_screen_active_users" in sample_names
