# Multi-stage build for StormLeads backend

# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies for PostGIS and spatial libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies for PostGIS
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgeos-c1v5 \
    libproj25 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Add local bin to PATH
ENV PATH=/root/.local/bin:$PATH

# Set Python unbuffered for better logging
ENV PYTHONUNBUFFERED=1

# Railway sets PORT environment variable
# Expose port for documentation (Railway ignores this)
EXPOSE 8000

# Run uvicorn - Railway provides $PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
