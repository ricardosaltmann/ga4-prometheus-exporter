"""Integration tests for Core Collector and multi-property isolation."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from google.api_core.exceptions import PermissionDenied

from ga4_exporter.collectors.core import CoreCollector
from ga4_exporter.config import AppConfig, PropertyConfig
from ga4_exporter.metrics.cache import MetricsCache
from ga4_exporter.metrics.internal import COLLECTOR_UP


def test_core_collector_multi_property_isolation():
    """Verify that failure in one property does not impact another property."""
    config = AppConfig(
        properties=[
            PropertyConfig(name="prop_ok", property_id="111111111"),
            PropertyConfig(name="prop_fail", property_id="222222222"),
        ],
    )
    cache = MetricsCache()
    mock_client = MagicMock()

    # Successful response for prop_ok
    mock_ok_resp = SimpleNamespace(
        rows=[
            SimpleNamespace(
                metric_values=[
                    SimpleNamespace(value="500"),  # activeUsers
                    SimpleNamespace(value="600"),  # totalUsers
                    SimpleNamespace(value="200"),  # newUsers
                    SimpleNamespace(value="1200"), # sessions
                    SimpleNamespace(value="900"),  # engagedSessions
                    SimpleNamespace(value="3500"), # screenPageViews
                    SimpleNamespace(value="8000"), # eventCount
                    SimpleNamespace(value="0.75"), # engagementRate
                    SimpleNamespace(value="0.25"), # bounceRate
                ]
            )
        ],
        property_quota=None,
    )

    def mock_run_core(property_id, **kwargs):
        if property_id == "111111111":
            return mock_ok_resp
        raise PermissionDenied("403 User does not have Viewer permission")

    mock_client.run_core_report.side_effect = mock_run_core

    collector_ok = CoreCollector(
        config=config,
        property_config=config.properties[0],
        client=mock_client,
        cache=cache,
    )
    collector_fail = CoreCollector(
        config=config,
        property_config=config.properties[1],
        client=mock_client,
        cache=cache,
    )

    # Run both collectors
    collector_ok.run()
    collector_fail.run()

    # prop_ok should be UP
    assert COLLECTOR_UP.labels(property="prop_ok", collector="core")._value.get() == 1
    # prop_fail should be DOWN
    assert COLLECTOR_UP.labels(property="prop_fail", collector="core")._value.get() == 0

    # Samples for prop_ok must be present
    samples = cache.get_all_samples()
    ok_samples = [s for s in samples if s.labels.get("property") == "prop_ok"]
    assert len(ok_samples) > 0

    sessions_sample = next(s for s in ok_samples if s.name == "ga4_sessions")
    assert sessions_sample.value == 1200.0
