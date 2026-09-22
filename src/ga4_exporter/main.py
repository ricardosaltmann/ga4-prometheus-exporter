"""CLI entrypoint and server runner for GA4 Prometheus Exporter."""

import argparse
import sys

import uvicorn

from ga4_exporter.api.app import create_app
from ga4_exporter.config import load_config
from ga4_exporter.google.auth import get_credentials
from ga4_exporter.google.client import GA4Client
from ga4_exporter.logging import setup_logging


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate configuration and credential files without running the server."""
    print(f"Validating configuration from: {args.config}")
    try:
        config = load_config(args.config)
        print("[OK] Configuration syntax and schema: VALID")
    except Exception as exc:
        print(f"[FAIL] Configuration error: {exc}")
        return 1

    # Validate properties
    print(f"Configured properties: {len(config.properties)}")
    for prop in config.properties:
        print(f"  - Property '{prop.name}' (ID: {prop.property_id}, enabled: {prop.enabled})")

    # Validate credentials accessibility
    print("\nValidating credentials:")
    try:
        _creds, project_id = get_credentials(config.google.credentials_file)
        target_info = config.google.credentials_file or "Application Default Credentials (ADC)"
        print(f"[OK] Credentials accessible: {target_info}")
        if project_id:
            print(f"[OK] GCP Project ID: {project_id}")
    except Exception as exc:
        print(f"[FAIL] Credentials validation failed: {exc}")
        return 1

    print("\n[OK] Validation completed successfully. Exporter is ready to run.")
    return 0


def cmd_test_connection(args: argparse.Namespace) -> int:
    """Test live connectivity to Google Analytics Data API for configured properties."""
    print(f"Testing GA4 connection using config: {args.config}")
    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"[FAIL] Failed to load configuration: {exc}")
        return 1

    try:
        client = GA4Client(
            credentials_file=config.google.credentials_file,
            timeout_seconds=config.google.timeout_seconds,
        )
        print("[OK] Google Analytics client initialized")
    except Exception as exc:
        print(f"[FAIL] Failed to initialize GA4 client: {exc}")
        return 1

    all_ok = True
    for prop in config.properties:
        if not prop.enabled:
            print(f"\nSkipping disabled property: {prop.name}")
            continue

        print(f"\nTesting property: '{prop.name}' (ID: {prop.property_id})")
        res = client.test_connection(prop.property_id)

        if res["realtime_ok"]:
            print("  [OK] Realtime query (runRealtimeReport) successful")
        else:
            print("  [FAIL] Realtime query failed")
            all_ok = False

        if res["core_ok"]:
            print("  [OK] Core query (runReport) successful")
        else:
            print("  [FAIL] Core query failed")
            all_ok = False

        if res["error"]:
            print(f"  [ERROR] {res['error']}")

    if all_ok:
        print("\n[OK] All enabled GA4 properties tested successfully!")
        return 0
    else:
        print("\n[FAIL] One or more GA4 property tests failed.")
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    """Run the GA4 Prometheus Exporter server."""
    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"Error loading configuration: {exc}", file=sys.stderr)
        return 1

    # Override config with CLI arguments if specified
    if args.log_level:
        config.logging.level = args.log_level
    if args.host:
        config.server.listen_address = args.host
    if args.port:
        config.server.port = args.port

    logger = setup_logging(level=config.logging.level, log_format=config.logging.format)
    logger.info(
        f"Starting GA4 Prometheus Exporter on {config.server.listen_address}:{config.server.port}"
    )

    app = create_app(config)

    uvicorn.run(
        app,
        host=config.server.listen_address,
        port=config.server.port,
        log_level=config.logging.level.lower(),
        access_log=False,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    config_parent = argparse.ArgumentParser(add_help=False)
    config_parent.add_argument(
        "-c", "--config",
        dest="config",
        default=None,
        help="Path to YAML configuration file (default: config.yaml or $GA4_CONFIG)",
    )

    parser = argparse.ArgumentParser(
        prog="ga4-exporter",
        description="Production-grade Google Analytics 4 (GA4) Prometheus Exporter",
        parents=[config_parent],
    )

    subparsers = parser.add_subparsers(dest="command")

    # Command: run (default)
    run_parser = subparsers.add_parser(
        "run", help="Run the exporter server (default)", parents=[config_parent]
    )
    run_parser.add_argument("--host", help="HTTP listen host")
    run_parser.add_argument("--port", type=int, help="HTTP listen port")
    run_parser.add_argument("--log-level", help="Log level (DEBUG, INFO, WARNING, ERROR)")

    # Command: validate
    subparsers.add_parser(
        "validate",
        help="Validate configuration and credentials without starting server",
        parents=[config_parent],
    )

    # Command: test-connection
    subparsers.add_parser(
        "test-connection",
        help="Test live connection to Google Analytics Data API",
        parents=[config_parent],
    )

    return parser


def cli_entrypoint() -> None:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args()

    # Default to run if no command given
    command = args.command or "run"

    if command == "validate":
        sys.exit(cmd_validate(args))
    elif command == "test-connection":
        sys.exit(cmd_test_connection(args))
    elif command == "run":
        sys.exit(cmd_run(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli_entrypoint()
