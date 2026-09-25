"""Unit tests for GA4 PropertyQuota parser."""

from types import SimpleNamespace

from ga4_exporter.google.quota import parse_property_quota


def test_parse_full_property_quota():
    """Test parsing a fully populated PropertyQuota object."""
    quota_mock = SimpleNamespace(
        tokens_per_hour=SimpleNamespace(consumed=58, remaining=39942),
        tokens_per_day=SimpleNamespace(consumed=1200, remaining=48800),
        tokens_per_project_per_hour=SimpleNamespace(consumed=150, remaining=19850),
        concurrent_requests=SimpleNamespace(consumed=1, remaining=9),
        server_errors_per_project_per_hour=SimpleNamespace(consumed=0, remaining=10),
    )

    parsed = parse_property_quota(quota_mock)
    assert parsed is not None
    assert parsed.tokens_per_hour.consumed == 58.0
    assert parsed.tokens_per_hour.remaining == 39942.0
    assert parsed.tokens_per_day.consumed == 1200.0
    assert parsed.tokens_per_day.remaining == 48800.0
    assert parsed.tokens_per_project_per_hour.consumed == 150.0
    assert parsed.tokens_per_project_per_hour.remaining == 19850.0
    assert parsed.concurrent_requests.consumed == 1.0
    assert parsed.concurrent_requests.remaining == 9.0


def test_parse_none_or_empty_quota():
    """Test handling when property_quota is None or empty."""
    assert parse_property_quota(None) is None
    assert parse_property_quota({}) is None


def test_parse_partial_dict_quota():
    """Test parsing a dictionary-based quota with partial fields."""
    dict_quota = {
        "tokens_per_hour": {"consumed": "10", "remaining": "990"},
        # other fields omitted
    }
    parsed = parse_property_quota(dict_quota)
    assert parsed is not None
    assert parsed.tokens_per_hour.consumed == 10.0
    assert parsed.tokens_per_hour.remaining == 990.0
    assert parsed.tokens_per_day is None
