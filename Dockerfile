FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md alembic.ini /app/
COPY src /app/src
COPY migrations /app/migrations
COPY infra /app/infra
COPY rulebook /app/rulebook
COPY scripts /app/scripts

RUN pip install .

RUN chmod +x /app/scripts/start_backend.sh

CMD ["/app/scripts/start_backend.sh"]
