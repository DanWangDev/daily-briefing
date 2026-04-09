FROM python:3.13-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

COPY config.example.yaml .

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "-m", "briefing"]
