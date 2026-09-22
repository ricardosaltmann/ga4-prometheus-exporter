"""Asynchronous background collection scheduler with concurrency locks and jitter."""

import asyncio
import logging

from ga4_exporter.collectors.base import BaseCollector
from ga4_exporter.collectors.core import CoreCollector
from ga4_exporter.collectors.realtime import RealtimeCollector
from ga4_exporter.config import AppConfig
from ga4_exporter.google.client import GA4Client
from ga4_exporter.metrics.cache import MetricsCache

logger = logging.getLogger("ga4_exporter")


class Scheduler:
    """Manages periodic execution of GA4 collectors."""

    def __init__(self, config: AppConfig, client: GA4Client, cache: MetricsCache) -> None:
        self.config = config
        self.client = client
        self.cache = cache
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._initial_scrape_completed = asyncio.Event()

        # Concurrency locks per (property, collector) to prevent overlapping executions
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._collectors: list[tuple[BaseCollector, int, float]] = []  # (collector, interval, initial_delay)

        self._setup_collectors()

    def _setup_collectors(self) -> None:
        """Instantiate enabled collectors with staggered jitter."""
        jitter_step_seconds = 5.0
        prop_idx = 0

        for prop in self.config.properties:
            if not prop.enabled:
                continue

            base_delay = prop_idx * jitter_step_seconds
            prop_idx += 1

            # 1. Realtime Collector
            if self.config.collection.realtime.enabled:
                rt_collector = RealtimeCollector(
                    config=self.config,
                    property_config=prop,
                    client=self.client,
                    cache=self.cache,
                )
                rt_interval = self.config.collection.realtime.interval_seconds
                self._collectors.append((rt_collector, rt_interval, base_delay))
                self._locks[(prop.name, "realtime")] = asyncio.Lock()

            # 2. Core Collector
            if self.config.collection.core.enabled:
                core_collector = CoreCollector(
                    config=self.config,
                    property_config=prop,
                    client=self.client,
                    cache=self.cache,
                )
                core_interval = self.config.collection.core.interval_seconds
                # Offset core delay slightly from realtime
                self._collectors.append((core_collector, core_interval, base_delay + 2.0))
                self._locks[(prop.name, "core")] = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        """Returns True if the initial collection attempts have finished."""
        return self._initial_scrape_completed.is_set()

    async def _run_loop(self, collector: BaseCollector, interval: int, initial_delay: float) -> None:
        """Periodic loop for a single collector with concurrency lock."""
        lock = self._locks[(collector.property_name, collector.name)]

        # Initial jitter delay
        if initial_delay > 0:
            try:
                await asyncio.sleep(initial_delay)
            except asyncio.CancelledError:
                return

        while self._running:
            # Acquire lock to ensure no overlapping execution of the same collector
            if lock.locked():
                logger.warning(
                    f"Collector {collector.property_name}/{collector.name} is already running. Skipping overlapping run to prevent API storm."
                )
            else:
                async with lock:
                    try:
                        # BaseCollector.run() handles metrics, timings, and exceptions safely
                        await asyncio.to_thread(collector.run)
                    except Exception as exc:
                        logger.error(
                            f"Unexpected scheduler error in {collector.property_name}/{collector.name}: {exc}"
                        )

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    async def start(self) -> None:
        """Start all scheduled background loops."""
        if self._running:
            return

        self._running = True
        logger.info(
            f"Starting background scheduler with {len(self._collectors)} active collectors..."
        )

        for collector, interval, delay in self._collectors:
            task = asyncio.create_task(
                self._run_loop(collector, interval, delay),
                name=f"collector-{collector.property_name}-{collector.name}",
            )
            self._tasks.append(task)

        # Launch background watcher to set initial_scrape_completed once at least one attempt completes
        asyncio.create_task(self._wait_for_initial_attempts())

    async def _wait_for_initial_attempts(self) -> None:
        """Wait briefly for initial attempts to register in cache for readiness."""
        await asyncio.sleep(1.0)
        self._initial_scrape_completed.set()

    async def stop(self) -> None:
        """Gracefully stop all collection tasks."""
        if not self._running:
            return

        logger.info("Stopping scheduler and cancelling running collection tasks...")
        self._running = False

        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Scheduler stopped cleanly.")
