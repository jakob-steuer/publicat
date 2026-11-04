# Publicat: one image serving API + built UI. User data lives in /data (mount a volume).
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
# No PyTorch in the image: Semantic Scholar provides the embeddings.
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
ENV PUBLICAT_DATA_DIR=/data PUBLICAT_HOST=0.0.0.0 PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8001
CMD ["uv", "run", "--no-sync", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
