"""Configuration models and loader for GA4 Prometheus Exporter."""

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

_PROMETHEUS_METRIC_NAME_REGEX = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
_NUMERIC_PROPERTY_ID_REGEX = re.compile(r"^\d+$")


class ServerConfig(BaseModel):
    """HTTP Server configuration."""
    listen_address: str = Field(default="0.0.0.0", description="IP address to bind the HTTP server to")
    port: int = Field(default=9674, ge=1024, le=65535, description="Port for the HTTP exporter")


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")
    format: str = Field(default="json", description="Log format: json or text")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid}")
        return upper

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        lower = v.lower()
        if lower not in {"json", "text"}:
            raise ValueError(f"Invalid log format: {v}. Must be 'json' or 'text'")
        return lower


class GoogleConfig(BaseModel):
    """Google Cloud and API configuration."""
    credentials_file: str | None = Field(
        default=None,
        description="Path to service account JSON key. If omitted, ADC is used."
    )
    timeout_seconds: int = Field(default=30, ge=5, le=120, description="API timeout in seconds")


class DateRangeConfig(BaseModel):
    """Date range window for core reports."""
    start_date: str = Field(default="today", description="Start date (e.g. 'today', 'yesterday', 'YYYY-MM-DD')")
    end_date: str = Field(default="today", description="End date (e.g. 'today', 'yesterday', 'YYYY-MM-DD')")


class RealtimeCollectionConfig(BaseModel):
    """Realtime report collection schedule."""
    enabled: bool = True
    interval_seconds: int = Field(default=60, ge=10, le=3600)


class CoreCollectionConfig(BaseModel):
    """Core report collection schedule."""
    enabled: bool = True
    interval_seconds: int = Field(default=300, ge=30, le=86400)
    date_range: DateRangeConfig = Field(default_factory=DateRangeConfig)


class CollectionConfig(BaseModel):
    """Collection scheduler configuration."""
    realtime: RealtimeCollectionConfig = Field(default_factory=RealtimeCollectionConfig)
    core: CoreCollectionConfig = Field(default_factory=CoreCollectionConfig)


class CacheConfig(BaseModel):
    """In-memory cache configuration."""
    stale_after_seconds: int = Field(default=900, ge=60, description="Cache retention after collection failure")


class PrometheusConfig(BaseModel):
    """Prometheus exposition options."""
    include_property_id_label: bool = Field(default=False, description="Whether to include property_id as label")
    max_series_per_query: int = Field(default=100, ge=1, le=1000, description="Max cardinality limit per query")


class QuotaConfig(BaseModel):
    """GA4 API quota monitoring."""
    enabled: bool = True


class MetricMapping(BaseModel):
    """Mapping between GA4 metric name and Prometheus metric name."""
    name: str = Field(..., description="GA4 API metric name, e.g. activeUsers")
    prometheus_name: str = Field(..., description="Exposed Prometheus name, e.g. ga4_realtime_active_users")

    @field_validator("prometheus_name")
    @classmethod
    def validate_prometheus_name(cls, v: str) -> str:
        if not _PROMETHEUS_METRIC_NAME_REGEX.match(v):
            raise ValueError(f"Invalid Prometheus metric name: {v}")
        if not v.startswith("ga4_"):
            raise ValueError(f"Prometheus metric name must start with 'ga4_': {v}")
        return v


class DimensionBreakdownConfig(BaseModel):
    """Safe dimension breakdown configuration."""
    name: str = Field(..., description="GA4 dimension name, e.g. deviceCategory")
    prometheus_label: str = Field(..., description="Prometheus label name, e.g. device_category")


class TopPagesConfig(BaseModel):
    """Top-N pages query configuration."""
    enabled: bool = False
    dimension: str = "pagePath"
    metric: str = "screenPageViews"
    limit: int = Field(default=20, ge=1, le=100)


class CustomEventConfig(BaseModel):
    """Explicitly tracked custom event."""
    name: str = Field(..., description="GA4 event name, e.g. login, purchase")
    enabled: bool = True


class BreakdownConfig(BaseModel):
    """Configuration for dimension breakdowns (e.g. devices, channels)."""
    enabled: bool = False
    limit: int = Field(default=10, ge=1, le=50)


class RealtimeScreensConfig(BaseModel):
    """Configuration for realtime screens."""
    enabled: bool = False
    limit: int = Field(default=10, ge=1, le=50)


class MetricsConfig(BaseModel):
    """Metrics mapping definitions."""
    realtime: list[MetricMapping] = Field(
        default_factory=lambda: [
            MetricMapping(name="activeUsers", prometheus_name="ga4_realtime_active_users")
        ]
    )
    core: list[MetricMapping] = Field(
        default_factory=lambda: [
            MetricMapping(name="activeUsers", prometheus_name="ga4_active_users"),
            MetricMapping(name="totalUsers", prometheus_name="ga4_total_users"),
            MetricMapping(name="newUsers", prometheus_name="ga4_new_users"),
            MetricMapping(name="sessions", prometheus_name="ga4_sessions"),
            MetricMapping(name="engagedSessions", prometheus_name="ga4_engaged_sessions"),
            MetricMapping(name="screenPageViews", prometheus_name="ga4_screen_page_views"),
            MetricMapping(name="eventCount", prometheus_name="ga4_event_count"),
            MetricMapping(name="engagementRate", prometheus_name="ga4_engagement_rate"),
            MetricMapping(name="bounceRate", prometheus_name="ga4_bounce_rate"),
        ]
    )
    safe_dimensions: list[DimensionBreakdownConfig] = Field(default_factory=list)
    top_pages: TopPagesConfig = Field(default_factory=TopPagesConfig)
    events: list[CustomEventConfig] = Field(default_factory=list)
    devices: BreakdownConfig = Field(default_factory=BreakdownConfig)
    traffic_channels: BreakdownConfig = Field(default_factory=BreakdownConfig)
    realtime_devices: BreakdownConfig = Field(default_factory=BreakdownConfig)
    realtime_screens: RealtimeScreensConfig = Field(default_factory=RealtimeScreensConfig)


class PropertyConfig(BaseModel):
    """Individual GA4 property configuration."""
    name: str = Field(..., min_length=1, description="Friendly property name for labels, e.g. portal")
    property_id: str = Field(..., description="Numeric GA4 Property ID, e.g. '123456789'")
    enabled: bool = True

    @field_validator("property_id")
    @classmethod
    def validate_property_id(cls, v: str) -> str:
        cleaned = v.strip()
        if not _NUMERIC_PROPERTY_ID_REGEX.match(cleaned):
            raise ValueError(f"Property ID must be numeric (e.g. '123456789'), got '{v}'. Do not use Measurement ID (G-XXXXX).")
        return cleaned


class AppConfig(BaseModel):
    """Main Application Configuration."""
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    google: GoogleConfig = Field(default_factory=GoogleConfig)
    properties: list[PropertyConfig] = Field(..., min_length=1)
    collection: CollectionConfig = Field(default_factory=CollectionConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    quota: QuotaConfig = Field(default_factory=QuotaConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)

    @model_validator(mode="after")
    def validate_unique_properties(self) -> "AppConfig":
        names = set()
        for prop in self.properties:
            if prop.name in names:
                raise ValueError(f"Duplicate property name detected in config: '{prop.name}'")
            names.add(prop.name)
        return self


def load_config(config_path: str | None = None) -> AppConfig:
    """Load configuration from file and apply environment variable overrides."""
    resolved_path = config_path or os.getenv("GA4_CONFIG", "config.yaml")

    data = {}
    path_obj = Path(resolved_path)
    if path_obj.exists():
        with open(path_obj, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    elif config_path is not None:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Environment overrides
    if "server" not in data:
        data["server"] = {}
    if os.getenv("GA4_LISTEN_ADDRESS"):
        data["server"]["listen_address"] = os.getenv("GA4_LISTEN_ADDRESS")
    if os.getenv("GA4_PORT"):
        data["server"]["port"] = int(os.getenv("GA4_PORT"))

    if "logging" not in data:
        data["logging"] = {}
    if os.getenv("GA4_LOG_LEVEL"):
        data["logging"]["level"] = os.getenv("GA4_LOG_LEVEL")

    if "google" not in data:
        data["google"] = {}
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        data["google"]["credentials_file"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    # Collection interval overrides
    if "collection" not in data:
        data["collection"] = {}
    if "realtime" not in data["collection"]:
        data["collection"]["realtime"] = {}
    if "core" not in data["collection"]:
        data["collection"]["core"] = {}

    rt_interval = os.getenv("GA4_REALTIME_INTERVAL_SECONDS") or os.getenv("GA4_REALTIME_INTERVAL")
    if rt_interval:
        data["collection"]["realtime"]["interval_seconds"] = int(rt_interval)

    core_interval = os.getenv("GA4_CORE_INTERVAL_SECONDS") or os.getenv("GA4_CORE_INTERVAL")
    if core_interval:
        data["collection"]["core"]["interval_seconds"] = int(core_interval)

    # Cache stale retention overrides
    if "cache" not in data:
        data["cache"] = {}
    stale_sec = os.getenv("GA4_CACHE_STALE_AFTER_SECONDS")
    if stale_sec:
        data["cache"]["stale_after_seconds"] = int(stale_sec)

    # Property ID override from environment (e.g. for containerized deploys)
    env_prop_id = os.getenv("GA4_PROPERTY_ID")
    if env_prop_id:
        env_prop_name = os.getenv("GA4_PROPERTY_NAME", "default")
        data["properties"] = [{"name": env_prop_name, "property_id": env_prop_id, "enabled": True}]

    return AppConfig.model_validate(data)

