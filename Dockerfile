# =============================================================================
# QuantEngine Pro - Production Docker Image
# =============================================================================
# Multi-stage build with minimal attack surface.
#
# Build:
#   docker build -t quantengine-pro:latest .
#
# Run:
#   docker run -p 8050:8050 -p 8000:8000 \
#     -e DEEPSEEK_API_KEY=sk-xxx \
#     -v $(pwd)/config:/app/config:ro \
#     -v $(pwd)/data:/app/data \
#     quantengine-pro:latest
# =============================================================================

# ---- Builder Stage ----
FROM python:3.12-slim AS builder

WORKDIR /app

ENV \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install build dependencies for native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Production Stage ----
FROM python:3.12-slim

WORKDIR /app

ENV \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/app

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code (order matters for layer caching: stable layers first)
COPY quantengine/ ./quantengine/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Create non-root user and set up data directories
RUN groupadd --system quant && \
    useradd --system --gid quant --create-home --shell /sbin/nologin quant && \
    mkdir -p /app/data/parquet /app/logs && \
    chown -R quant:quant /app && \
    chmod -R 755 /app/quantengine /app/scripts

# Metadata labels
LABEL \
    org.opencontainers.image.title="QuantEngine Pro" \
    org.opencontainers.image.description="Full-featured quantitative trading system" \
    org.opencontainers.image.source="https://github.com/quantengine/pro" \
    org.opencontainers.image.version="0.1.0" \
    org.opencontainers.image.vendor="QuantEngine Team"

USER quant

# Expose ports: 8050 (Dash dashboard) / 8000 (FastAPI)
EXPOSE 8050 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Default command
CMD ["python", "-m", "quantengine.web.app", "--host", "0.0.0.0", "--port", "8050"]
