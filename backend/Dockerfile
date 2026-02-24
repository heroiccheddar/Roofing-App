FROM python:3.12-slim

# Install GDAL and spatial libs for geopandas/shapely/rasterio
RUN apt-get update && apt-get install -y \
    gdal-bin libgdal-dev g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for volume mount
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
EXPOSE 8080
