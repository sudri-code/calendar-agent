FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ /build/shared/
COPY worker/pyproject.toml /build/worker/
RUN pip install --no-cache-dir /build/shared/

COPY worker/ /build/worker/
RUN pip install --no-cache-dir /build/worker/

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY shared/ /app/shared/
COPY worker/ /app/worker/
COPY api/ /app/api/

WORKDIR /app/worker

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

CMD ["celery", "-A", "celery_config", "worker", "--loglevel=info", "-B"]
