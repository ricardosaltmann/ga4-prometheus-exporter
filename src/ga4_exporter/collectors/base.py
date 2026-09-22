"""Base collector class managing metrics, timing, and error classification."""

import abc
import logging
import time

from google.api_core.exceptions import (
    DeadlineExceeded,
    GoogleAPICallError,
    InvalidArgument,
    PermissionDenied,
    ResourceExhausted,
    Unauthenticated,
)

from ga4_exporter.config import AppConfig, PropertyConfig
from ga4_exporter.google.client import GA4Client
from ga4_exporter.metrics.cache import MetricsCache
from ga4_exporter.metrics.internal import (
    API_ERRORS_TOTAL,
    API_REQUEST_DURATION,
    API_REQUESTS_TOTAL,
)

logger = logging.getLogger("ga4_exporter")


def classify_error(exc: BaseException) -> str:
    """Classify exceptions into controlled, bounded Prometheus error types."""
    if isinstance(exc, ResourceExhausted):
        return "quota_exceeded"
    if isinstance(exc, PermissionDenied):
        return "permission_denied"
    if isinstance(exc, Unauthenticated):
        return "auth_error"
    if isinstance(exc, InvalidArgument):
        return "client_error"
    if isinstance(exc, (DeadlineExceeded, TimeoutError)):
        return "timeout"
    if isinstance(exc, GoogleAPICallError):
        code = getattr(exc, "code", None)
        if callable(code):
            try:
                code = code()
            except Exception:
                code = None
        if code == 429:
            return "quota_exceeded"
        if code in (401, 403):
            return "auth_error"
        if code and 400 <= code < 500:
            return "client_error"
        if code and code >= 500:
            return "server_error"
    if isinstance(exc, ConnectionError):
        return "connection_error"
    return "unknown_error"


class BaseCollector(abc.ABC):
    """Abstract base collector for GA4 data."""

    def __init__(
        self,
        name: str,
        config: AppConfig,
        property_config: PropertyConfig,
        client: GA4Client,
        cache: MetricsCache,
    ) -> None:
        self.name = name
        self.config = config
        self.property_config = property_config
        self.client = client
        self.cache = cache
        self.property_name = property_config.name
        self.property_id = property_config.property_id

    @abc.abstractmethod
    def collect(self) -> None:
        """Execute the collection logic and update the cache."""

    def run(self) -> None:
        """Run collection with error tracking, timing, and metric updates."""
        self.cache.record_attempt(self.property_name, self.name)
        start_time = time.perf_counter()
        status = "success"
        error_type: str | None = None
        error_msg: str | None = None

        try:
            self.collect()
        except Exception as exc:
            status = "failed"
            error_type = classify_error(exc)
            error_msg = str(exc)
            logger.error(
                f"Collection failed for property={self.property_name} collector={self.name}: {error_msg}",
                extra={
                    "property": self.property_name,
                    "collector": self.name,
                    "status": "failed",
                    "error_type": error_type,
                },
            )
            API_ERRORS_TOTAL.labels(
                property=self.property_name,
                collector=self.name,
                error_type=error_type,
            ).inc()
            self.cache.update_failure(self.property_name, self.name, error_msg)
        finally:
            duration = time.perf_counter() - start_time
            API_REQUEST_DURATION.labels(
                property=self.property_name,
                collector=self.name,
            ).observe(duration)
            API_REQUESTS_TOTAL.labels(
                property=self.property_name,
                collector=self.name,
                status=status,
            ).inc()
