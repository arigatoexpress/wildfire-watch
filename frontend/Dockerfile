# wildfire-watch admin frontend — Cloud Run image
#
# Build:
#   docker build -f frontend/Dockerfile -t gcr.io/tho-ai-agent/wildfire-frontend .
# Run:
#   docker run -p 8080:8080 -e ADMIN_TOKEN=dev gcr.io/tho-ai-agent/wildfire-frontend
#
# Cloud Run deploy:
#   gcloud run deploy wildfire-frontend \
#     --image gcr.io/tho-ai-agent/wildfire-frontend \
#     --region us-central1 \
#     --project tho-ai-agent \
#     --allow-unauthenticated \
#     --set-env-vars=ADMIN_TOKEN=...

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install only what the frontend needs. The heavier ML stack stays out
# of this image so the Cloud Run cold-start is fast.
RUN pip install --no-cache-dir \
        flask==3.0.3 \
        gunicorn==22.0.0

# Copy source (frontend module + AOR geojson + fixture).
COPY frontend/ /app/frontend/
COPY missions/ /app/missions/
# Optional sink — empty in the image; signals come from a writable
# volume / GCS sync in production.
RUN mkdir -p /app/data

EXPOSE 8080

# 2 workers x 4 threads is a fine default for a read-heavy dashboard.
CMD exec gunicorn \
    --bind :${PORT} \
    --workers 2 \
    --threads 4 \
    --timeout 30 \
    --access-logfile - \
    "frontend.app:create_app()"
