"""GA4 Metadata and compatibility checking module."""

import logging
from typing import Any

logger = logging.getLogger("ga4_exporter")


class MetadataValidator:
    """Validates GA4 metrics and dimensions using API metadata."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_property_metadata(self, property_id: str) -> tuple[set[str], set[str]]:
        """Fetch available metrics and dimensions for a property.

        Returns:
            Tuple of (metric_names, dimension_names)
        """
        property_path = f"properties/{property_id}"
        metrics: set[str] = set()
        dimensions: set[str] = set()

        try:
            metadata = self._client.get_metadata(name=f"{property_path}/metadata")
            for m in getattr(metadata, "metrics", []):
                metrics.add(getattr(m, "api_name", ""))
            for d in getattr(metadata, "dimensions", []):
                dimensions.add(getattr(d, "api_name", ""))
        except Exception as exc:
            logger.warning(
                f"Failed to fetch metadata for {property_path}: {exc}. Proceeding with config metrics."
            )

        return metrics, dimensions

    def check_compatibility(
        self, property_id: str, dimensions: list[str], metrics: list[str]
    ) -> bool:
        """Check if combination of dimensions and metrics is compatible."""
        property_path = f"properties/{property_id}"
        try:
            # check_compatibility API call if supported
            resp = self._client.check_compatibility(
                property=property_path,
                dimensions=[{"name": d} for d in dimensions],
                metrics=[{"name": m} for m in metrics],
            )
            # If compatibility issues returned, log them
            incompatibilities = getattr(resp, "dimension_compatibilities", [])
            for item in incompatibilities:
                status = getattr(item, "compatibility", None)
                if str(status) == "INCOMPATIBLE":
                    dim_name = getattr(getattr(item, "dimension_metadata", None), "api_name", "unknown")
                    logger.warning(f"Dimension '{dim_name}' is incompatible for property {property_id}")
                    return False
            return True
        except Exception as exc:
            logger.debug(f"checkCompatibility skipped or failed for {property_path}: {exc}")
            return True
