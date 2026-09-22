"""Parser and data structures for GA4 PropertyQuota."""

from dataclasses import dataclass
from typing import Any


@dataclass
class QuotaMetricValues:
    consumed: float
    remaining: float


@dataclass
class ParsedPropertyQuota:
    tokens_per_day: QuotaMetricValues | None = None
    tokens_per_hour: QuotaMetricValues | None = None
    tokens_per_project_per_hour: QuotaMetricValues | None = None
    concurrent_requests: QuotaMetricValues | None = None
    server_errors_per_project_per_hour: QuotaMetricValues | None = None


def _parse_quota_status(quota_obj: Any) -> QuotaMetricValues | None:
    """Parse a single QuotaStatus proto message or dictionary."""
    if quota_obj is None:
        return None

    # Handle protobuf / object attributes or dict items
    consumed = getattr(quota_obj, "consumed", None)
    remaining = getattr(quota_obj, "remaining", None)

    if consumed is None and isinstance(quota_obj, dict):
        consumed = quota_obj.get("consumed")
    if remaining is None and isinstance(quota_obj, dict):
        remaining = quota_obj.get("remaining")

    if consumed is not None and remaining is not None:
        try:
            return QuotaMetricValues(consumed=float(consumed), remaining=float(remaining))
        except (ValueError, TypeError):
            return None
    return None


def parse_property_quota(quota_obj: Any) -> ParsedPropertyQuota | None:
    """Parse the PropertyQuota object from a GA4 API response."""
    if not quota_obj:
        return None

    tokens_per_day = _parse_quota_status(getattr(quota_obj, "tokens_per_day", None) or (quota_obj.get("tokens_per_day") if isinstance(quota_obj, dict) else None))
    tokens_per_hour = _parse_quota_status(getattr(quota_obj, "tokens_per_hour", None) or (quota_obj.get("tokens_per_hour") if isinstance(quota_obj, dict) else None))
    tokens_per_project_per_hour = _parse_quota_status(getattr(quota_obj, "tokens_per_project_per_hour", None) or (quota_obj.get("tokens_per_project_per_hour") if isinstance(quota_obj, dict) else None))
    concurrent_requests = _parse_quota_status(getattr(quota_obj, "concurrent_requests", None) or (quota_obj.get("concurrent_requests") if isinstance(quota_obj, dict) else None))
    server_errors = _parse_quota_status(getattr(quota_obj, "server_errors_per_project_per_hour", None) or (quota_obj.get("server_errors_per_project_per_hour") if isinstance(quota_obj, dict) else None))

    return ParsedPropertyQuota(
        tokens_per_day=tokens_per_day,
        tokens_per_hour=tokens_per_hour,
        tokens_per_project_per_hour=tokens_per_project_per_hour,
        concurrent_requests=concurrent_requests,
        server_errors_per_project_per_hour=server_errors,
    )
