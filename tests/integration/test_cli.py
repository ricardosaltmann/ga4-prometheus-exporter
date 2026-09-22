"""Integration tests for CLI commands (validate, test-connection)."""

import argparse
from unittest.mock import MagicMock, patch

from ga4_exporter.main import cmd_test_connection, cmd_validate


def test_cli_validate_success(tmp_path):
    """Test CLI validate command with valid config and readable credentials."""
    dummy_key = tmp_path / "sa.json"
    dummy_key.write_text('{"type": "service_account", "project_id": "test-project"}')

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
properties:
  - name: portal
    property_id: "123456789"
google:
  credentials_file: "{str(dummy_key).replace('\\', '/')}"
""")

    args = argparse.Namespace(config=str(cfg_file))

    with patch("ga4_exporter.main.get_credentials") as mock_get_creds:
        mock_get_creds.return_value = (MagicMock(), "test-project")
        code = cmd_validate(args)

    assert code == 0


def test_cli_validate_invalid_config(tmp_path):
    """Test CLI validate command with invalid config syntax."""
    cfg_file = tmp_path / "bad_config.yaml"
    cfg_file.write_text("""
properties:
  - name: portal
    property_id: "G-INVALID" # Must be numeric
""")

    args = argparse.Namespace(config=str(cfg_file))
    code = cmd_validate(args)
    assert code == 1


def test_cli_test_connection_success(tmp_path):
    """Test CLI test-connection command when GA4 queries succeed."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
properties:
  - name: portal
    property_id: "123456789"
""")

    args = argparse.Namespace(config=str(cfg_file))

    with patch("ga4_exporter.main.GA4Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.test_connection.return_value = {
            "property_id": "123456789",
            "reachable": True,
            "realtime_ok": True,
            "core_ok": True,
            "error": None,
        }
        mock_client_cls.return_value = mock_instance

        code = cmd_test_connection(args)

    assert code == 0


def test_cli_test_connection_failure(tmp_path):
    """Test CLI test-connection command when GA4 query fails."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
properties:
  - name: portal
    property_id: "123456789"
""")

    args = argparse.Namespace(config=str(cfg_file))

    with patch("ga4_exporter.main.GA4Client") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.test_connection.return_value = {
            "property_id": "123456789",
            "reachable": False,
            "realtime_ok": False,
            "core_ok": False,
            "error": "PermissionDenied (403)",
        }
        mock_client_cls.return_value = mock_instance

        code = cmd_test_connection(args)

    assert code == 1
