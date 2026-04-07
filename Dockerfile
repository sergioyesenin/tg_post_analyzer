FROM node:22-bookworm-slim AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-base.txt requirements-ai.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -r requirements-base.txt -r requirements-ai.txt

COPY . .
COPY --from=frontend-build /frontend/dist /app/frontend/dist

RUN mkdir -p /app/runtime

EXPOSE 8000

CMD ["python", "scripts/run_api.py", "--host", "0.0.0.0", "--port", "8000"]
