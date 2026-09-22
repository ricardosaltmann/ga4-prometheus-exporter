"""Unit tests for GA4Client retry policy and error classification."""

from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import (
    DeadlineExceeded,
    InternalServerError,
    InvalidArgument,
    PermissionDenied,
    ResourceExhausted,
    Unauthenticated,
)

from ga4_exporter.google.client import GA4Client, _is_transient_error


def test_is_transient_error_classification():
    """Verify that only transient errors qualify for retries."""
    # Transient errors
    assert _is_transient_error(ResourceExhausted("429 Quota")) is True
    assert _is_transient_error(InternalServerError("500 Error")) is True
    assert _is_transient_error(DeadlineExceeded("504 Timeout")) is True
    assert _is_transient_error(TimeoutError("Socket timeout")) is True

    # Non-transient errors
    assert _is_transient_error(PermissionDenied("403 Forbidden")) is False
    assert _is_transient_error(Unauthenticated("401 Unauthorized")) is False
    assert _is_transient_error(InvalidArgument("400 Bad Request")) is False


def test_client_retries_transient_error_until_success():
    """Verify GA4Client retries when transient error occurs and succeeds on subsequent attempt."""
    mock_raw_client = MagicMock()
    # Fail first with ResourceExhausted, then return valid response
    valid_response = MagicMock()
    valid_response.rows = []
    mock_raw_client.run_realtime_report.side_effect = [
        ResourceExhausted("429 rate limit"),
        valid_response,
    ]

    client = GA4Client(client=mock_raw_client, timeout_seconds=5)
    resp = client.run_realtime_report("123456789", ["activeUsers"])

    assert resp == valid_response
    assert mock_raw_client.run_realtime_report.call_count == 2


def test_client_fails_immediately_without_retry_on_permission_denied():
    """Verify that 403 PermissionDenied fails immediately without retry loop."""
    mock_raw_client = MagicMock()
    mock_raw_client.run_realtime_report.side_effect = PermissionDenied("403 Viewer role missing")

    client = GA4Client(client=mock_raw_client, timeout_seconds=5)
    with pytest.raises(PermissionDenied):
        client.run_realtime_report("123456789", ["activeUsers"])

    # Must be called exactly once (no retry!)
    assert mock_raw_client.run_realtime_report.call_count == 1
