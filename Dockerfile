# =============================================================================
# QuantEngine Pro - Docker Image
# =============================================================================
# Multi-stage build for a lean production image.
#
# Build:
#   docker build -t quantengine-pro:latest .
#
# Run:
#   docker run -p 8050:8050 -p 8000:8000 \
#     -e DEEPSEEK_API_KEY=sk-xxx \
#     -v $(pwd)/config:/app/config \
#     -v $(pwd)/data:/app/data \
#     quantengine-pro:latest
# =============================================================================

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Production Stage ----
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Ensure scripts in the user bin directory are on PATH
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY quantengine/ ./quantengine/
COPY config/ ./config/
COPY scripts/ ./scripts/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash quant && \
    mkdir -p /app/data/parquet /app/logs && \
    chown -R quant:quant /app

USER quant

# Expose ports
# 8050: Dash dashboard
# 8000: FastAPI backend
EXPOSE 8050 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Default command: start web application
CMD ["python", "-m", "quantengine.web.app", "--host", "0.0.0.0", "--port", "8050"]
