FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
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

CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/switchpilot.conf"]
