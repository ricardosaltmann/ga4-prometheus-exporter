"""Realtime report collector using GA4 runRealtimeReport."""

import logging
import time

from ga4_exporter.collectors.base import BaseCollector
from ga4_exporter.google.quota import parse_property_quota
from ga4_exporter.metrics.ga4 import MetricSample

logger = logging.getLogger("ga4_exporter")


class RealtimeCollector(BaseCollector):
    """Collector for GA4 Realtime metrics."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(name="realtime", *args, **kwargs)

    def collect(self) -> None:
        start_ms = time.perf_counter()
        samples: list[MetricSample] = []

        # 1. Prepare metrics and dimensions
        metric_mappings = self.config.metrics.realtime
        metric_names = [m.name for m in metric_mappings]
        dimension_names = [d.name for d in self.config.metrics.safe_dimensions]

        # 2. Call GA4 API
        response = self.client.run_realtime_report(
            property_id=self.property_id,
            metric_names=metric_names,
            dimension_names=dimension_names if dimension_names else None,
            return_property_quota=self.config.quota.enabled,
        )

        rows = getattr(response, "rows", [])
        base_labels: dict[str, str] = {"property": self.property_name}
        if self.config.prometheus.include_property_id_label:
            base_labels["property_id"] = self.property_id

        # 3. Process data rows
        if not rows:
            # When GA4 returns no active users in the window, emit 0 for each configured metric
            for mapping in metric_mappings:
                samples.append(
                    MetricSample(
                        name=mapping.prometheus_name,
                        labels=dict(base_labels),
                        value=0.0,
                    )
                )
        else:
            for row in rows:
                row_labels = dict(base_labels)
                # Map dimensions if present
                for idx, dim_val in enumerate(getattr(row, "dimension_values", [])):
                    if idx < len(self.config.metrics.safe_dimensions):
                        label_name = self.config.metrics.safe_dimensions[idx].prometheus_label
                        row_labels[label_name] = dim_val.value

                # Map metric values
                for idx, metric_val in enumerate(getattr(row, "metric_values", [])):
                    if idx < len(metric_mappings):
                        prom_name = metric_mappings[idx].prometheus_name
                        try:
                            val = float(metric_val.value)
                        except (ValueError, TypeError):
                            val = 0.0
                        samples.append(
                            MetricSample(
                                name=prom_name,
                                labels=dict(row_labels),
                                value=val,
                            )
                        )

        # 4. Extract quotas if enabled
        if self.config.quota.enabled and hasattr(response, "property_quota"):
            quota = parse_property_quota(response.property_quota)
            if quota:
                quota_labels = {"property": self.property_name, "quota_type": "realtime"}
                if self.config.prometheus.include_property_id_label:
                    quota_labels["property_id"] = self.property_id

                if quota.tokens_per_hour:
                    samples.append(
                        MetricSample(
                            name="ga4_api_quota_tokens_per_hour_remaining",
                            labels=dict(quota_labels),
                            value=quota.tokens_per_hour.remaining,
                        )
                    )
                    samples.append(
                        MetricSample(
                            name="ga4_api_quota_tokens_per_hour_consumed",
                            labels=dict(quota_labels),
                            value=quota.tokens_per_hour.consumed,
                        )
                    )
                if quota.tokens_per_day:
                    samples.append(
                        MetricSample(
                            name="ga4_api_quota_tokens_per_day_remaining",
                            labels=dict(quota_labels),
                            value=quota.tokens_per_day.remaining,
                        )
                    )
                    samples.append(
                        MetricSample(
                            name="ga4_api_quota_tokens_per_day_consumed",
                            labels=dict(quota_labels),
                            value=quota.tokens_per_day.consumed,
                        )
                    )
                if quota.concurrent_requests:
                    samples.append(
                        MetricSample(
                            name="ga4_api_quota_concurrent_requests_remaining",
                            labels=dict(quota_labels),
                            value=quota.concurrent_requests.remaining,
                        )
                    )
                    samples.append(
                        MetricSample(
                            name="ga4_api_quota_concurrent_requests_consumed",
                            labels=dict(quota_labels),
                            value=quota.concurrent_requests.consumed,
                        )
                    )

        # 5. Update cache with fresh samples
        self.cache.update_success(self.property_name, self.name, samples)

        duration_ms = round((time.perf_counter() - start_ms) * 1000, 2)
        logger.info(
            f"Collected realtime metrics for {self.property_name} ({len(samples)} samples, {len(rows)} rows)",
            extra={
                "component": "collector",
                "property": self.property_name,
                "collector": "realtime",
                "status": "success",
                "duration_ms": duration_ms,
                "rows": len(rows),
            },
        )
