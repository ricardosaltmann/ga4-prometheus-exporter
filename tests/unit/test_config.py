"""Unit tests for configuration validation."""

import pytest
from pydantic import ValidationError

from ga4_exporter.config import AppConfig, MetricMapping, PropertyConfig, load_config


def test_valid_property_config():
    """Test valid property configurations."""
    prop = PropertyConfig(name="portal", property_id="123456789")
    assert prop.name == "portal"
    assert prop.property_id == "123456789"
    assert prop.enabled is True


def test_invalid_property_id_non_numeric():
    """Test that measurement IDs or non-numeric IDs fail validation."""
    with pytest.raises(ValidationError) as exc:
        PropertyConfig(name="portal", property_id="G-ABC123456")
    assert "Property ID must be numeric" in str(exc.value)


def test_duplicate_property_names_rejected():
    """Test that duplicate property names raise ValueError."""
    data = {
        "properties": [
            {"name": "portal", "property_id": "111111111"},
            {"name": "portal", "property_id": "222222222"},
        ]
    }
    with pytest.raises(ValidationError) as exc:
        AppConfig.model_validate(data)
    assert "Duplicate property name detected" in str(exc.value)


def test_prometheus_metric_name_validation():
    """Test that Prometheus metric names must start with ga4_ and be valid syntax."""
    with pytest.raises(ValidationError) as exc:
        MetricMapping(name="activeUsers", prometheus_name="invalid-name")
    assert "Invalid Prometheus metric name" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        MetricMapping(name="activeUsers", prometheus_name="custom_active_users")
    assert "Prometheus metric name must start with 'ga4_'" in str(exc.value)

    valid = MetricMapping(name="activeUsers", prometheus_name="ga4_valid_metric_name")
    assert valid.prometheus_name == "ga4_valid_metric_name"


def test_environment_variable_overrides(monkeypatch, tmp_path):
    """Test that environment variables override configuration file settings."""
    cfg_file = tmp_path / "test_config.yaml"
    cfg_file.write_text("""
server:
  listen_address: "127.0.0.1"
  port: 8000
logging:
  level: "INFO"
properties:
  - name: "test_prop"
    property_id: "999999999"
""")

    monkeypatch.setenv("GA4_PORT", "9674")
    monkeypatch.setenv("GA4_LISTEN_ADDRESS", "0.0.0.0")
    monkeypatch.setenv("GA4_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/mock-key.json")

    config = load_config(str(cfg_file))
    assert config.server.port == 9674
    assert config.server.listen_address == "0.0.0.0"
    assert config.logging.level == "DEBUG"
    assert config.google.credentials_file == "/tmp/mock-key.json"
