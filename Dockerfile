# No BuildKit-only syntax here: Docker 20.10 (Synology, Debian 12) and docker-compose v1 build this too
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
LABEL org.opencontainers.image.title="SwitchPilot" \
      org.opencontainers.image.description="Web management for Xikestor SKS3200-8E2X switches" \
      org.opencontainers.image.source="https://github.com/altzone/xike_manager" \
      org.opencontainers.image.licenses="MIT" \
      com.centurylinklabs.watchtower.enable="false"
RUN apt-get update && apt-get install -y nginx supervisor && rm -rf /var/lib/apt/lists/*

# Backend
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Frontend
COPY --from=frontend-build /build/dist /app/frontend
COPY frontend/nginx.conf /etc/nginx/sites-available/default
RUN rm -f /etc/nginx/sites-enabled/default && \
    ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

# Supervisor
COPY supervisord.conf /etc/supervisor/conf.d/switchpilot.conf

# Data volume
RUN mkdir -p /app/data
VOLUME /app/data
ENV DB_PATH=/app/data/switchpilot.db

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1/api/setup/status', timeout=4).status == 200 else 1)"

CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/switchpilot.conf"]
