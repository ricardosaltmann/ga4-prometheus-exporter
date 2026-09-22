"""Unit tests for cardinality enforcement and series limits."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from ga4_exporter.collectors.core import CoreCollector
from ga4_exporter.config import AppConfig, PropertyConfig
from ga4_exporter.metrics.cache import MetricsCache
from ga4_exporter.metrics.internal import SERIES_DROPPED_TOTAL


def test_top_pages_cardinality_limit_and_dropped_counter():
    """Verify that top-N queries truncate at limit and increment series dropped counter."""
    config = AppConfig(
        properties=[PropertyConfig(name="portal", property_id="123456789")],
        prometheus={"max_series_per_query": 5},
        metrics={
            "top_pages": {
                "enabled": True,
                "dimension": "pagePath",
                "metric": "screenPageViews",
                "limit": 3,
            }
        },
    )

    cache = MetricsCache()
    mock_client = MagicMock()

    # Core main report response
    main_resp = SimpleNamespace(
        rows=[
            SimpleNamespace(
                metric_values=[SimpleNamespace(value="100") for _ in config.metrics.core]
            )
        ]
    )

    # Top pages response returning 10 pages (exceeding limit of 3)
    top_rows = [
        SimpleNamespace(
            dimension_values=[SimpleNamespace(value=f"/page-{i}")],
            metric_values=[SimpleNamespace(value=str(100 - i))],
        )
        for i in range(10)
    ]
    top_resp = SimpleNamespace(rows=top_rows)

    mock_client.run_core_report.side_effect = [main_resp, top_resp]

    collector = CoreCollector(
        config=config,
        property_config=config.properties[0],
        client=mock_client,
        cache=cache,
    )

    initial_dropped = SERIES_DROPPED_TOTAL.labels(property="portal", collector="core")._value.get()
    collector.collect()

    samples = cache.get_all_samples()
    page_samples = [s for s in samples if s.name == "ga4_top_page_views"]

    # Should be strictly capped at limit (3)
    assert len(page_samples) == 3

    # Dropped counter should reflect the truncated series
    new_dropped = SERIES_DROPPED_TOTAL.labels(property="portal", collector="core")._value.get()
    assert new_dropped > initial_dropped
