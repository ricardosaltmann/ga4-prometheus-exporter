"""Authentication utilities for Google Analytics Data API."""

import os
from pathlib import Path

import google.auth
from google.oauth2 import service_account

GA4_READONLY_SCOPE = ["https://www.googleapis.com/auth/analytics.readonly"]


def get_credentials(credentials_file: str | None = None) -> tuple[google.auth.credentials.Credentials, str | None]:
    """Retrieve Google credentials via Service Account JSON file or Application Default Credentials (ADC).

    Returns:
        A tuple of (credentials, project_id)
    """
    # 1. Explicit credentials file parameter or GOOGLE_APPLICATION_CREDENTIALS
    target_file = credentials_file or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if target_file:
        file_path = Path(target_file)
        if not file_path.is_file():
            raise FileNotFoundError(f"Service Account key file not found: {file_path.name}")
        if not os.access(file_path, os.R_OK):
            raise PermissionError(f"Service Account key file is not readable: {file_path.name}")

        credentials = service_account.Credentials.from_service_account_file(
            str(file_path),
            scopes=GA4_READONLY_SCOPE,
        )
        project_id = getattr(credentials, "project_id", None)
        return credentials, project_id

    # 2. Application Default Credentials (ADC)
    try:
        credentials, project_id = google.auth.default(scopes=GA4_READONLY_SCOPE)
        return credentials, project_id
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load Google Application Default Credentials: {exc}. "
            "Please provide a Service Account JSON file or set GOOGLE_APPLICATION_CREDENTIALS."
        ) from exc
