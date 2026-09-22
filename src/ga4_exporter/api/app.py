"""FastAPI application exposing /metrics, /health, /ready, and /status."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from ga4_exporter.config import AppConfig
from ga4_exporter.google.client import GA4Client
from ga4_exporter.metrics.cache import MetricsCache
from ga4_exporter.metrics.internal import init_internal_metrics
from ga4_exporter.metrics.registry import setup_prometheus_registry
from ga4_exporter.scheduler.scheduler import Scheduler


def create_app(
    config: AppConfig,
    client: GA4Client | None = None,
    cache: MetricsCache | None = None,
    scheduler: Scheduler | None = None,
    registry: CollectorRegistry | None = None,
) -> FastAPI:
    """Application factory for GA4 Prometheus Exporter."""

    # Initialize components if not provided (e.g. Injected in tests)
    app_cache = cache or MetricsCache(stale_after_seconds=config.cache.stale_after_seconds)
    app_client = client or GA4Client(
        credentials_file=config.google.credentials_file,
        timeout_seconds=config.google.timeout_seconds,
    )
    app_scheduler = scheduler or Scheduler(
        config=config,
        client=app_client,
        cache=app_cache,
    )

    init_internal_metrics()
    app_registry = setup_prometheus_registry(app_cache, registry=registry)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        await app_scheduler.start()
        yield
        # Shutdown
        await app_scheduler.stop()

    app = FastAPI(
        title="GA4 Prometheus Exporter",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # Attach components for route access
    app.state.config = config
    app.state.client = app_client
    app.state.cache = app_cache
    app.state.scheduler = app_scheduler
    app.state.registry = app_registry

    @app.get("/metrics", response_class=Response)
    async def metrics():
        """Expose collected Prometheus metrics (decoupled from live API calls)."""
        output = generate_latest(app.state.registry)
        return Response(content=output, media_type=CONTENT_TYPE_LATEST)

    @app.get("/health", response_class=JSONResponse)
    async def health():
        """Liveness probe: verifies process is alive and operational."""
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})

    @app.get("/ready", response_class=JSONResponse)
    async def ready():
        """Readiness probe: verifies initial configuration, credentials, and collectors ready."""
        if app.state.scheduler.is_ready:
            return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready"})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "initializing", "message": "Collectors have not completed initial run"},
        )

    @app.get("/status", response_class=JSONResponse)
    async def exporter_status():
        """Sanitized operational status summary (never leaks credentials)."""
        summary = app.state.cache.get_status_summary()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "operational",
                "properties": summary,
            },
        )

    return app
