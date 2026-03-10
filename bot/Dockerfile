FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ /build/shared/
COPY bot/pyproject.toml /build/bot/
RUN pip install --no-cache-dir /build/shared/

COPY bot/ /build/bot/
RUN pip install --no-cache-dir /build/bot/

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY shared/ /app/shared/
COPY bot/ /app/bot/

WORKDIR /app/bot

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "main.py"]
