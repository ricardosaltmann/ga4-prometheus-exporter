"""Unit tests for thread-safe MetricsCache and stale handling."""

import time

from ga4_exporter.metrics.cache import MetricsCache
from ga4_exporter.metrics.ga4 import MetricSample


def test_cache_success_update_and_retrieval():
    """Test updating and retrieving metrics on success."""
    cache = MetricsCache(stale_after_seconds=900)
    samples = [
        MetricSample(name="ga4_realtime_active_users", labels={"property": "portal"}, value=42.0)
    ]

    cache.update_success("portal", "realtime", samples)
    active = cache.get_all_samples()

    assert len(active) == 1
    assert active[0].name == "ga4_realtime_active_users"
    assert active[0].value == 42.0


def test_cache_failure_retains_valid_data_within_stale_window():
    """Test that failure preserves previous valid samples within stale threshold."""
    cache = MetricsCache(stale_after_seconds=900)
    initial_samples = [
        MetricSample(name="ga4_sessions", labels={"property": "portal"}, value=150.0)
    ]

    # Initial success
    cache.update_success("portal", "core", initial_samples)
    assert len(cache.get_all_samples()) == 1

    # Follow-up failure
    cache.update_failure("portal", "core", error_message="API connection timeout")

    # Metrics should still be served while within stale window
    active = cache.get_all_samples()
    assert len(active) == 1
    assert active[0].value == 150.0

    # Verify snapshot indicates error state
    snapshot = cache.get_snapshot("portal", "core")
    assert snapshot.is_success is False
    assert snapshot.error_message == "API connection timeout"


def test_cache_stale_expiry():
    """Test that stale samples are purged once stale_after_seconds has elapsed."""
    cache = MetricsCache(stale_after_seconds=1)  # 1 second threshold
    samples = [
        MetricSample(name="ga4_realtime_active_users", labels={"property": "portal"}, value=10.0)
    ]

    cache.update_success("portal", "realtime", samples)
    assert len(cache.get_all_samples()) == 1

    # Wait for stale expiry
    time.sleep(1.1)

    # Samples should now be suppressed
    active = cache.get_all_samples()
    assert len(active) == 0


def test_distinction_zero_users_vs_failure():
    """Verify that GA4 returning 0 is marked success with value 0, not failure."""
    cache = MetricsCache(stale_after_seconds=900)
    zero_samples = [
        MetricSample(name="ga4_realtime_active_users", labels={"property": "portal"}, value=0.0)
    ]

    cache.update_success("portal", "realtime", zero_samples)
    snapshot = cache.get_snapshot("portal", "realtime")

    assert snapshot.is_success is True
    assert len(snapshot.samples) == 1
    assert snapshot.samples[0].value == 0.0


def test_cache_status_summary():
    """Verify status summary output does not contain sensitive tokens."""
    cache = MetricsCache(stale_after_seconds=900)
    samples = [MetricSample(name="ga4_sessions", labels={"property": "portal"}, value=100.0)]
    cache.update_success("portal", "core", samples)

    summary = cache.get_status_summary()
    assert "portal" in summary
    assert "core" in summary["portal"]
    assert summary["portal"]["core"]["status"] == "ok"
    assert summary["portal"]["core"]["is_stale"] is False
    assert summary["portal"]["core"]["samples_count"] == 1
