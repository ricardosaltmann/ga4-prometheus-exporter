"""Google Analytics Data API client wrapper with resilience, retries, and isolation."""

import logging
from typing import Any

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    FilterExpression,
    Metric,
    RunRealtimeReportRequest,
    RunReportRequest,
)
from google.api_core.client_info import ClientInfo
from google.api_core.exceptions import (
    DeadlineExceeded,
    InternalServerError,
    InvalidArgument,
    PermissionDenied,
    ResourceExhausted,
    ServiceUnavailable,
    Unauthenticated,
)
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from ga4_exporter import __version__
from ga4_exporter.google.auth import get_credentials
from ga4_exporter.google.metadata import MetadataValidator

logger = logging.getLogger("ga4_exporter")


def _is_transient_error(exception: BaseException) -> bool:
    """Determine whether an exception should be retried."""
    if isinstance(exception, (ResourceExhausted, ServiceUnavailable, InternalServerError, DeadlineExceeded)):
        return True
    if isinstance(exception, (PermissionDenied, Unauthenticated, InvalidArgument)):
        return False
    if isinstance(exception, (ConnectionResetError, TimeoutError)):
        return True
    # Check status code if present
    code = getattr(exception, "code", None)
    if callable(code):
        try:
            code = code()
        except Exception:
            code = None
    return code in (429, 500, 502, 503, 504)


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    """Log retry attempts without sensitive information."""
    logger.warning(
        f"Retrying GA4 API call after error (attempt {retry_state.attempt_number}): {retry_state.outcome.exception() if retry_state.outcome else 'unknown'}"
    )


class GA4Client:
    """Isolated client for Google Analytics Data API."""

    def __init__(
        self,
        credentials_file: str | None = None,
        timeout_seconds: int = 30,
        client: Any | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._custom_client = client

        if client is not None:
            self._client = client
        else:
            credentials, _ = get_credentials(credentials_file)
            client_info = ClientInfo(user_agent=f"ga4-prometheus-exporter/{__version__}")
            self._client = BetaAnalyticsDataClient(
                credentials=credentials,
                client_info=client_info,
            )

        self._metadata_validator = MetadataValidator(self._client)

    @property
    def metadata_validator(self) -> MetadataValidator:
        return self._metadata_validator

    @retry(
        retry=retry_if_exception(_is_transient_error),
        wait=wait_random_exponential(multiplier=1, max=10),
        stop=stop_after_attempt(4),
        before_sleep=_log_retry_attempt,
        reraise=True,
    )
    def run_realtime_report(
        self,
        property_id: str,
        metric_names: list[str],
        dimension_names: list[str] | None = None,
        return_property_quota: bool = True,
    ) -> Any:
        """Execute a runRealtimeReport call with retries and timeout."""
        property_path = f"properties/{property_id}"
        metrics = [Metric(name=name) for name in metric_names]
        dimensions = [Dimension(name=name) for name in (dimension_names or [])]

        request = RunRealtimeReportRequest(
            property=property_path,
            metrics=metrics,
            dimensions=dimensions,
            return_property_quota=return_property_quota,
        )

        return self._client.run_realtime_report(
            request=request,
            timeout=float(self.timeout_seconds),
        )

    @retry(
        retry=retry_if_exception(_is_transient_error),
        wait=wait_random_exponential(multiplier=1, max=10),
        stop=stop_after_attempt(4),
        before_sleep=_log_retry_attempt,
        reraise=True,
    )
    def run_core_report(
        self,
        property_id: str,
        metric_names: list[str],
        start_date: str = "today",
        end_date: str = "today",
        dimension_names: list[str] | None = None,
        dimension_filter: FilterExpression | None = None,
        limit: int | None = None,
        return_property_quota: bool = True,
    ) -> Any:
        """Execute a runReport call with retries and timeout."""
        property_path = f"properties/{property_id}"
        metrics = [Metric(name=name) for name in metric_names]
        dimensions = [Dimension(name=name) for name in (dimension_names or [])]
        date_ranges = [DateRange(start_date=start_date, end_date=end_date)]

        request = RunReportRequest(
            property=property_path,
            metrics=metrics,
            dimensions=dimensions,
            date_ranges=date_ranges,
            dimension_filter=dimension_filter,
            limit=limit,
            return_property_quota=return_property_quota,
        )

        return self._client.run_report(
            request=request,
            timeout=float(self.timeout_seconds),
        )

    def test_connection(self, property_id: str) -> dict[str, Any]:
        """Test API connectivity and basic permissions on a property."""
        results: dict[str, Any] = {
            "property_id": property_id,
            "reachable": False,
            "realtime_ok": False,
            "core_ok": False,
            "error": None,
        }
        try:
            # 1. Test realtime with 1 activeUser metric
            self.run_realtime_report(
                property_id=property_id,
                metric_names=["activeUsers"],
                return_property_quota=True,
            )
            results["reachable"] = True
            results["realtime_ok"] = True

            # 2. Test core report with sessions
            self.run_core_report(
                property_id=property_id,
                metric_names=["sessions"],
                start_date="today",
                end_date="today",
                return_property_quota=True,
            )
            results["core_ok"] = True
        except PermissionDenied:
            results["error"] = (
                "PermissionDenied (403): The Service Account does not have Viewer access "
                f"to GA4 property {property_id} in Property Access Management."
            )
        except Unauthenticated as exc:
            results["error"] = f"Unauthenticated (401): Invalid credentials. ({exc})"
        except Exception as exc:
            results["error"] = str(exc)

        return results
