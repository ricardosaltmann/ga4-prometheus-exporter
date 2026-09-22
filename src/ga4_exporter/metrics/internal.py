"""Internal exporter telemetry and operational metrics."""

import sys

from prometheus_client import Counter, Gauge, Histogram

from ga4_exporter import __version__

# 1. Global Exporter Health
EXPORTER_UP = Gauge(
    "ga4_exporter_up",
    "Whether the GA4 Prometheus Exporter is running and healthy (1 = healthy, 0 = critical error)",
)

# 2. Build Info
BUILD_INFO = Gauge(
    "ga4_exporter_build_info",
    "Static build and runtime information for the GA4 exporter",
    ["version", "python"],
)

# 3. Collector Status per property and collector
COLLECTOR_UP = Gauge(
    "ga4_exporter_collector_up",
    "Whether the last collection run succeeded (1 = success, 0 = failure)",
    ["property", "collector"],
)

# 4. Timestamps
LAST_SUCCESS_TIMESTAMP = Gauge(
    "ga4_exporter_last_success_timestamp_seconds",
    "Unix timestamp in seconds of the last successful GA4 API collection",
    ["property", "collector"],
)

LAST_ATTEMPT_TIMESTAMP = Gauge(
    "ga4_exporter_last_attempt_timestamp_seconds",
    "Unix timestamp in seconds of the last GA4 API collection attempt",
    ["property", "collector"],
)

# 5. API Duration Histogram
API_REQUEST_DURATION = Histogram(
    "ga4_exporter_api_request_duration_seconds",
    "Duration of GA4 API requests in seconds",
    ["property", "collector"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0),
)

# 6. API Requests Counter
API_REQUESTS_TOTAL = Counter(
    "ga4_exporter_api_requests_total",
    "Total number of GA4 API requests made",
    ["property", "collector", "status"],
)

# 7. API Errors Counter
API_ERRORS_TOTAL = Counter(
    "ga4_exporter_api_errors_total",
    "Total number of errors encountered during GA4 API calls",
    ["property", "collector", "error_type"],
)

# 8. Cache Age Gauge
CACHE_AGE_SECONDS = Gauge(
    "ga4_exporter_cache_age_seconds",
    "Age in seconds of the currently cached data since last successful collection",
    ["property", "collector"],
)

# 9. Cardinality Drops Counter
SERIES_DROPPED_TOTAL = Counter(
    "ga4_exporter_series_dropped_total",
    "Total number of series dropped due to configured cardinality limits",
    ["property", "collector"],
)


ALL_INTERNAL_METRICS = [
    EXPORTER_UP,
    BUILD_INFO,
    COLLECTOR_UP,
    LAST_SUCCESS_TIMESTAMP,
    LAST_ATTEMPT_TIMESTAMP,
    API_REQUEST_DURATION,
    API_REQUESTS_TOTAL,
    API_ERRORS_TOTAL,
    CACHE_AGE_SECONDS,
    SERIES_DROPPED_TOTAL,
]


def init_internal_metrics() -> None:
    """Initialize base values for internal metrics."""
    EXPORTER_UP.set(1)
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    BUILD_INFO.labels(version=__version__, python=py_version).set(1)

