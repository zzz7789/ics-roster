# syntax=docker/dockerfile:1

# ---- 阶段 1：构建前端 ----
FROM node:22-alpine AS web
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
# 覆盖 vite.config.js 的默认 outDir（本地是 backend/static），产物放到容器内 /build/static
RUN npm run build -- --outDir /build/static --emptyOutDir

# ---- 阶段 2：运行后端 ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    ICS_ROSTER_DB=/data/ics-roster.db \
    ICS_ROSTER_DIST=/app/static

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=web /build/static /app/static

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
