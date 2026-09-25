"""Core report collector using GA4 runReport for aggregated metrics."""

import logging
import time

from google.analytics.data_v1beta.types import Filter, FilterExpression

from ga4_exporter.collectors.base import BaseCollector
from ga4_exporter.google.quota import parse_property_quota
from ga4_exporter.metrics.ga4 import MetricSample
from ga4_exporter.metrics.internal import SERIES_DROPPED_TOTAL

logger = logging.getLogger("ga4_exporter")


class CoreCollector(BaseCollector):
    """Collector for GA4 Core aggregated metrics."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(name="core", *args, **kwargs)

    def collect(self) -> None:
        start_ms = time.perf_counter()
        samples: list[MetricSample] = []
        total_rows = 0

        metric_mappings = self.config.metrics.core
        start_date = self.config.collection.core.date_range.start_date
        end_date = self.config.collection.core.date_range.end_date

        base_labels: dict[str, str] = {"property": self.property_name}
        if self.config.prometheus.include_property_id_label:
            base_labels["property_id"] = self.property_id

        # 1. Main Core Aggregate Query (chunked to respect GA4 10-metrics limit per request)
        quota_response = None
        chunk_size = 10
        chunks = [
            metric_mappings[i : i + chunk_size]
            for i in range(0, len(metric_mappings), chunk_size)
        ]

        for chunk_idx, chunk in enumerate(chunks):
            chunk_metric_names = [m.name for m in chunk]
            resp = self.client.run_core_report(
                property_id=self.property_id,
                metric_names=chunk_metric_names,
                start_date=start_date,
                end_date=end_date,
                return_property_quota=self.config.quota.enabled if chunk_idx == 0 else False,
            )
            if chunk_idx == 0:
                quota_response = resp

            rows = getattr(resp, "rows", [])
            total_rows += len(rows)

            if not rows:
                for mapping in chunk:
                    samples.append(
                        MetricSample(
                            name=mapping.prometheus_name,
                            labels=dict(base_labels),
                            value=0.0,
                        )
                    )
            else:
                first_row = rows[0]
                for idx, metric_val in enumerate(getattr(first_row, "metric_values", [])):
                    if idx < len(chunk):
                        prom_name = chunk[idx].prometheus_name
                        try:
                            val = float(metric_val.value)
                        except (ValueError, TypeError):
                            val = 0.0
                        samples.append(
                            MetricSample(
                                name=prom_name,
                                labels=dict(base_labels),
                                value=val,
                            )
                        )


        # 2. Top-N Pages (if enabled)
        top_pages_cfg = self.config.metrics.top_pages
        if top_pages_cfg.enabled:
            limit = min(top_pages_cfg.limit, self.config.prometheus.max_series_per_query)
            try:
                top_resp = self.client.run_core_report(
                    property_id=self.property_id,
                    metric_names=[top_pages_cfg.metric],
                    dimension_names=[top_pages_cfg.dimension],
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit + 1,  # Request 1 extra to detect truncation
                    return_property_quota=False,
                )
                top_rows = getattr(top_resp, "rows", [])
                total_rows += len(top_rows)

                # Check for series dropped
                if len(top_rows) > limit:
                    dropped_count = len(top_rows) - limit
                    SERIES_DROPPED_TOTAL.labels(
                        property=self.property_name, collector=self.name
                    ).inc(dropped_count)
                    top_rows = top_rows[:limit]

                for row in top_rows:
                    page_path = row.dimension_values[0].value
                    try:
                        page_views = float(row.metric_values[0].value)
                    except (ValueError, TypeError):
                        page_views = 0.0

                    labels = dict(base_labels)
                    labels["page"] = page_path
                    samples.append(
                        MetricSample(
                            name="ga4_top_page_views",
                            labels=labels,
                            value=page_views,
                        )
                    )
            except Exception as exc:
                logger.warning(f"Failed to fetch top pages for {self.property_name}: {exc}")

        # 3. Custom Events tracking (if enabled)
        configured_events = [e.name for e in self.config.metrics.events if e.enabled]
        if configured_events:
            try:
                # Query with eventName dimension filtered by configured events
                filter_expr = FilterExpression(
                    filter=Filter(
                        field_name="eventName",
                        in_list_filter=Filter.InListFilter(values=configured_events),
                    )
                )
                events_resp = self.client.run_core_report(
                    property_id=self.property_id,
                    metric_names=["eventCount"],
                    dimension_names=["eventName"],
                    dimension_filter=filter_expr,
                    start_date=start_date,
                    end_date=end_date,
                    return_property_quota=False,
                )
                events_rows = getattr(events_resp, "rows", [])
                total_rows += len(events_rows)

                # Track reported events
                seen_events = set()
                for row in events_rows:
                    event_name = row.dimension_values[0].value
                    seen_events.add(event_name)
                    try:
                        count = float(row.metric_values[0].value)
                    except (ValueError, TypeError):
                        count = 0.0

                    labels = dict(base_labels)
                    labels["event"] = event_name
                    samples.append(
                        MetricSample(
                            name="ga4_event_count",
                            labels=labels,
                            value=count,
                        )
                    )

                # For events configured but not triggered, report 0
                for event_name in configured_events:
                    if event_name not in seen_events:
                        labels = dict(base_labels)
                        labels["event"] = event_name
                        samples.append(
                            MetricSample(
                                name="ga4_event_count",
                                labels=labels,
                                value=0.0,
                            )
                        )
            except Exception as exc:
                logger.warning(f"Failed to fetch custom events for {self.property_name}: {exc}")

        # 4. Devices breakdown (if enabled)
        if self.config.metrics.devices.enabled:
            try:
                dev_resp = self.client.run_core_report(
                    property_id=self.property_id,
                    metric_names=["activeUsers", "sessions", "screenPageViews"],
                    dimension_names=["deviceCategory"],
                    start_date=start_date,
                    end_date=end_date,
                    limit=self.config.metrics.devices.limit,
                    return_property_quota=False,
                )
                for row in getattr(dev_resp, "rows", []):
                    device = row.dimension_values[0].value
                    labels = dict(base_labels)
                    labels["device"] = device
                    try:
                        u_val = float(row.metric_values[0].value)
                    except (ValueError, TypeError):
                        u_val = 0.0
                    try:
                        s_val = float(row.metric_values[1].value)
                    except (ValueError, TypeError):
                        s_val = 0.0
                    try:
                        p_val = float(row.metric_values[2].value)
                    except (ValueError, TypeError):
                        p_val = 0.0

                    samples.append(MetricSample(name="ga4_device_active_users", labels=labels, value=u_val))
                    samples.append(MetricSample(name="ga4_device_sessions", labels=labels, value=s_val))
                    samples.append(MetricSample(name="ga4_device_screen_page_views", labels=labels, value=p_val))
            except Exception as exc:
                logger.warning(f"Failed to fetch device breakdown for {self.property_name}: {exc}")

        # 5. Traffic channels breakdown (if enabled)
        if self.config.metrics.traffic_channels.enabled:
            try:
                tc_resp = self.client.run_core_report(
                    property_id=self.property_id,
                    metric_names=["sessions", "activeUsers"],
                    dimension_names=["sessionDefaultChannelGroup"],
                    start_date=start_date,
                    end_date=end_date,
                    limit=self.config.metrics.traffic_channels.limit,
                    return_property_quota=False,
                )
                for row in getattr(tc_resp, "rows", []):
                    channel = row.dimension_values[0].value
                    labels = dict(base_labels)
                    labels["channel"] = channel
                    try:
                        s_val = float(row.metric_values[0].value)
                    except (ValueError, TypeError):
                        s_val = 0.0
                    try:
                        u_val = float(row.metric_values[1].value)
                    except (ValueError, TypeError):
                        u_val = 0.0

                    samples.append(MetricSample(name="ga4_traffic_channel_sessions", labels=labels, value=s_val))
                    samples.append(MetricSample(name="ga4_traffic_channel_users", labels=labels, value=u_val))
            except Exception as exc:
                logger.warning(f"Failed to fetch traffic channels for {self.property_name}: {exc}")

        # 6. Extract quotas from main report
        if self.config.quota.enabled and quota_response and hasattr(quota_response, "property_quota"):
            quota = parse_property_quota(quota_response.property_quota)
            if quota:
                quota_labels = {"property": self.property_name, "quota_type": "core"}
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
            f"Collected core metrics for {self.property_name} ({len(samples)} samples, {total_rows} rows)",
            extra={
                "component": "collector",
                "property": self.property_name,
                "collector": "core",
                "status": "success",
                "duration_ms": duration_ms,
                "rows": total_rows,
            },
        )
