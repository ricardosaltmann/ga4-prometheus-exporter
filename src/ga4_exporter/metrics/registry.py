"""Prometheus custom collector and registry exposition."""

import contextlib
import math
from collections.abc import Iterable

from prometheus_client import REGISTRY, CollectorRegistry
from prometheus_client.core import GaugeMetricFamily

from ga4_exporter.metrics.cache import MetricsCache
from ga4_exporter.metrics.ga4 import GA4_METRIC_DOCS, MetricSample
from ga4_exporter.metrics.internal import ALL_INTERNAL_METRICS


class GA4CustomCollector:
    """Custom Prometheus Collector dynamically pulling from MetricsCache."""

    def __init__(self, cache: MetricsCache) -> None:
        self.cache = cache

    def collect(self) -> Iterable[GaugeMetricFamily]:
        """Collect all active cached GA4 metrics."""
        samples: list[MetricSample] = self.cache.get_all_samples()

        # Group samples by metric name
        grouped: dict[str, list[MetricSample]] = {}
        for sample in samples:
            # Skip invalid values (NaN, Inf)
            if math.isnan(sample.value) or math.isinf(sample.value):
                continue
            grouped.setdefault(sample.name, []).append(sample)

        for name, sample_list in grouped.items():
            first = sample_list[0]
            label_names = sorted(list(first.labels.keys()))
            doc = first.documentation or GA4_METRIC_DOCS.get(name, f"GA4 metric: {name}")

            gauge = GaugeMetricFamily(name, doc, labels=label_names)
            for s in sample_list:
                label_values = [s.labels.get(ln, "") for ln in label_names]
                gauge.add_metric(label_values, s.value)

            yield gauge


def setup_prometheus_registry(
    cache: MetricsCache, registry: CollectorRegistry | None = None
) -> CollectorRegistry:
    """Register the GA4 custom collector in the specified or default Prometheus REGISTRY."""
    target_registry = registry or REGISTRY
    collector = GA4CustomCollector(cache)

    with target_registry._lock:
        to_unregister = [
            reg
            for reg in getattr(target_registry, "_collector_to_names", {})
            if isinstance(reg, GA4CustomCollector)
        ]
    for reg in to_unregister:
        with contextlib.suppress(Exception):
            target_registry.unregister(reg)

    target_registry.register(collector)

    # If using an isolated custom registry, also register internal metrics
    if target_registry is not REGISTRY:
        with target_registry._lock:
            existing = set(target_registry._collector_to_names.keys())
        for metric in ALL_INTERNAL_METRICS:
            if metric not in existing:
                with contextlib.suppress(ValueError):
                    target_registry.register(metric)

    return target_registry

