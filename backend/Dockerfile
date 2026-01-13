# ===================================
# Stage 1: Builder
# ===================================
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /build

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
# Use pip to install from pyproject.toml, including scheduler extras for production
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -e ".[scheduler]"

# ===================================
# Stage 2: Runtime
# ===================================
FROM python:3.11-slim AS runtime

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Production mode by default
    NAS_MODE=prod \
    # Bind to all interfaces
    HOST=0.0.0.0 \
    PORT=8000

# Install runtime system dependencies
# - libpq5: PostgreSQL client library
# - smartmontools: SMART disk monitoring (smartctl)
# - mdadm: RAID management (optional, for production deployments)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    smartmontools \
    mdadm \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r baluhost && \
    useradd -r -g baluhost -u 1000 -m -s /bin/bash baluhost

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=baluhost:baluhost . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/storage /app/backups /app/tmp /app/logs && \
    chown -R baluhost:baluhost /app

# Switch to non-root user
USER baluhost

# Expose port
EXPOSE 8000

# Health check
# Checks if the FastAPI app responds on the health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/system/health').read()" || exit 1

# Default command: Run uvicorn
# Can be overridden in docker-compose.yml or at runtime
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
