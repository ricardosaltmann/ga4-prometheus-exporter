"""Structured logging for GA4 Prometheus Exporter."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

# Regex patterns for masking sensitive information
_SENSITIVE_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[^-]+-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r'("private_key"\s*:\s*)"[^"]+"'), r'\1"[REDACTED]"'),
    (re.compile(r'("private_key_id"\s*:\s*)"[^"]+"'), r'\1"[REDACTED]"'),
    (re.compile(r'(Bearer\s+)[A-Za-z0-9_\-\.]+'), r"\1[REDACTED_TOKEN]"),
    (re.compile(r'("token"\s*:\s*)"[^"]+"'), r'\1"[REDACTED]"'),
    (re.compile(r'("access_token"\s*:\s*)"[^"]+"'), r'\1"[REDACTED]"'),
]


def sanitize_message(msg: str) -> str:
    """Sanitize sensitive information from log messages."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter producing structured logs without sensitive data."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", "exporter"),
            "message": sanitize_message(record.getMessage()),
        }

        # Extra structured attributes
        for field in ("property", "collector", "status", "duration_ms", "rows", "error_type", "version"):
            val = getattr(record, field, None)
            if val is not None:
                log_entry[field] = val

        if record.exc_info and record.exc_text:
            log_entry["exception"] = sanitize_message(record.exc_text)

        return json.dumps(log_entry)


class TextFormatter(logging.Formatter):
    """Clean text formatter for development environments."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        msg = sanitize_message(record.getMessage())
        component = getattr(record, "component", "exporter")
        extra_info = []

        for field in ("property", "collector", "status", "duration_ms", "rows", "error_type"):
            val = getattr(record, field, None)
            if val is not None:
                extra_info.append(f"{field}={val}")

        extra_str = f" [{', '.join(extra_info)}]" if extra_info else ""
        formatted = f"{timestamp} [{record.levelname:<5}] [{component}] {msg}{extra_str}"
        if record.exc_info and record.exc_text:
            formatted += f"\n{sanitize_message(record.exc_text)}"
        return formatted


def setup_logging(level: str = "INFO", log_format: str = "json") -> logging.Logger:
    """Configure the root logger and return the application logger."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if log_format.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root_logger.addHandler(handler)

    # Suppress verbose logs from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    return logging.getLogger("ga4_exporter")
