"""GA4 business metric definitions and data structures."""

from dataclasses import dataclass, field


@dataclass
class MetricSample:
    """Represents a single Prometheus metric sample."""
    name: str
    labels: dict[str, str]
    value: float
    documentation: str = ""


# Default documentation for well-known GA4 metrics
GA4_METRIC_DOCS = {
    "ga4_realtime_active_users": "Current realtime active users (last 30 minutes)",
    "ga4_active_users": "Active users in the configured report window",
    "ga4_total_users": "Total users in the configured report window",
    "ga4_new_users": "Number of users who interacted with your site/app for the first time",
    "ga4_sessions": "Number of sessions that began on your site or app",
    "ga4_engaged_sessions": "Number of sessions that lasted 10+ seconds, had 2+ page views, or 1+ conversion event",
    "ga4_screen_page_views": "Total number of mobile app screens and web pages viewed",
    "ga4_event_count": "Total count of events triggered",
    "ga4_engagement_rate": "Percentage of engaged sessions (engagedSessions / sessions)",
    "ga4_bounce_rate": "Percentage of sessions that were not engaged (1 - engagementRate)",
    "ga4_average_session_duration_seconds": "Average duration of user sessions in seconds",
    "ga4_top_page_views": "Top page views by page path",
    # Quota metrics
    "ga4_api_quota_tokens_per_day_remaining": "Remaining GA4 API tokens for today for the property",
    "ga4_api_quota_tokens_per_day_consumed": "Consumed GA4 API tokens today for the property",
    "ga4_api_quota_tokens_per_hour_remaining": "Remaining GA4 API tokens for the current hour",
    "ga4_api_quota_tokens_per_hour_consumed": "Consumed GA4 API tokens in the current hour",
    "ga4_api_quota_tokens_per_project_per_hour_remaining": "Remaining GA4 API tokens per project per hour",
    "ga4_api_quota_tokens_per_project_per_hour_consumed": "Consumed GA4 API tokens per project per hour",
    "ga4_api_quota_concurrent_requests_remaining": "Remaining concurrent GA4 API requests",
    "ga4_api_quota_concurrent_requests_consumed": "Consumed concurrent GA4 API requests",
    "ga4_api_quota_server_errors_remaining": "Remaining allowed server errors per project per hour",
    "ga4_api_quota_server_errors_consumed": "Consumed server errors per project per hour",
}


@dataclass
class CollectionSnapshot:
    """Snapshot of metrics gathered by a single collector run."""
    property_name: str
    collector_name: str
    timestamp: float
    is_success: bool
    samples: list[MetricSample] = field(default_factory=list)
    error_message: str | None = None
