# ==============================================================================
# Stage 1: Builder
# ==============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ==============================================================================
# Stage 2: Final Minimal Runtime
# ==============================================================================
FROM python:3.12-slim AS runtime

# Create non-root system group and user
RUN groupadd -g 10001 ga4exporter && \
    useradd -u 10001 -g ga4exporter -s /bin/false -m ga4exporter

WORKDIR /app

# Install curl for container HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python dependencies from builder
COPY --from=builder /install /usr/local

# Copy application source code
COPY pyproject.toml README.md ./
COPY src/ /app/src/

# Install application in editable or site-packages
RUN pip install --no-cache-dir --no-deps -e .

# Security hardening: read-only filesystem friendliness
USER 10001:10001

EXPOSE 9674

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9674/health || exit 1

ENTRYPOINT ["ga4-exporter"]
CMD ["run"]
