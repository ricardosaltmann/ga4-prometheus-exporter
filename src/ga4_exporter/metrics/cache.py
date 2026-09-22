"""Thread-safe in-memory cache with stale data handling."""

import threading
import time
from typing import Any

from ga4_exporter.metrics.ga4 import CollectionSnapshot, MetricSample
from ga4_exporter.metrics.internal import (
    CACHE_AGE_SECONDS,
    COLLECTOR_UP,
    LAST_ATTEMPT_TIMESTAMP,
    LAST_SUCCESS_TIMESTAMP,
)


class MetricsCache:
    """Thread-safe in-memory cache storing collection snapshots per property and collector."""

    def __init__(self, stale_after_seconds: int = 900) -> None:
        self.stale_after_seconds = stale_after_seconds
        self._lock = threading.RLock()
        # Key: (property_name, collector_name) -> CollectionSnapshot
        self._snapshots: dict[tuple[str, str], CollectionSnapshot] = {}
        # Track last success timestamp explicitly
        self._last_success: dict[tuple[str, str], float] = {}

    def record_attempt(self, property_name: str, collector_name: str) -> None:
        """Record an attempt timestamp."""
        now = time.time()
        LAST_ATTEMPT_TIMESTAMP.labels(property=property_name, collector=collector_name).set(now)

    def update_success(
        self,
        property_name: str,
        collector_name: str,
        samples: list[MetricSample],
    ) -> None:
        """Store fresh successful collection results."""
        now = time.time()
        key = (property_name, collector_name)
        snapshot = CollectionSnapshot(
            property_name=property_name,
            collector_name=collector_name,
            timestamp=now,
            is_success=True,
            samples=samples,
        )

        with self._lock:
            self._snapshots[key] = snapshot
            self._last_success[key] = now

        # Update telemetry
        COLLECTOR_UP.labels(property=property_name, collector=collector_name).set(1)
        LAST_SUCCESS_TIMESTAMP.labels(property=property_name, collector=collector_name).set(now)
        CACHE_AGE_SECONDS.labels(property=property_name, collector=collector_name).set(0)

    def update_failure(
        self,
        property_name: str,
        collector_name: str,
        error_message: str,
    ) -> None:
        """Record a collection failure without discarding valid cached metrics immediately."""
        now = time.time()
        key = (property_name, collector_name)

        with self._lock:
            existing = self._snapshots.get(key)
            if existing:
                # Keep existing samples but mark failure in snapshot
                self._snapshots[key] = CollectionSnapshot(
                    property_name=property_name,
                    collector_name=collector_name,
                    timestamp=existing.timestamp,
                    is_success=False,
                    samples=existing.samples,
                    error_message=error_message,
                )
            else:
                self._snapshots[key] = CollectionSnapshot(
                    property_name=property_name,
                    collector_name=collector_name,
                    timestamp=now,
                    is_success=False,
                    samples=[],
                    error_message=error_message,
                )

        COLLECTOR_UP.labels(property=property_name, collector=collector_name).set(0)

    def get_all_samples(self) -> list[MetricSample]:
        """Retrieve all active, non-stale metric samples."""
        now = time.time()
        active_samples: list[MetricSample] = []

        with self._lock:
            for (prop, coll), snapshot in list(self._snapshots.items()):
                last_ok = self._last_success.get((prop, coll))
                if last_ok:
                    age = now - last_ok
                    CACHE_AGE_SECONDS.labels(property=prop, collector=coll).set(age)

                    if age <= self.stale_after_seconds:
                        active_samples.extend(snapshot.samples)
                    else:
                        # Stale limit exceeded: stop publishing business metrics from this snapshot
                        pass
                else:
                    # Never succeeded yet
                    CACHE_AGE_SECONDS.labels(property=prop, collector=coll).set(-1)

        return active_samples

    def get_snapshot(self, property_name: str, collector_name: str) -> CollectionSnapshot | None:
        """Get snapshot for a specific property and collector."""
        with self._lock:
            return self._snapshots.get((property_name, collector_name))

    def get_status_summary(self) -> dict[str, Any]:
        """Generate a clean status dictionary for the /status endpoint without sensitive data."""
        now = time.time()
        result: dict[str, Any] = {}

        with self._lock:
            for (prop, coll), snapshot in self._snapshots.items():
                if prop not in result:
                    result[prop] = {}
                last_ok = self._last_success.get((prop, coll))
                age = (now - last_ok) if last_ok else None
                is_stale = (age is not None and age > self.stale_after_seconds)

                result[prop][coll] = {
                    "last_attempt_timestamp": snapshot.timestamp,
                    "last_success_timestamp": last_ok,
                    "cache_age_seconds": round(age, 2) if age is not None else None,
                    "is_stale": is_stale,
                    "status": "ok" if snapshot.is_success else "error",
                    "samples_count": len(snapshot.samples),
                }

        return result
