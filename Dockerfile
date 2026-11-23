FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv

FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS builder

WORKDIR /app

ARG TIMEZONE=Asia/Jakarta

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=${TIMEZONE} \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv

# The lockfile is mandatory and must match pyproject.toml. Extras match the production Compose stack.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-editable --no-install-project \
    --extra redis --extra clickhouse --extra prometheus

COPY routemq ./routemq
COPY bootstrap ./bootstrap
RUN uv sync --locked --no-dev --no-editable \
    --extra redis --extra clickhouse --extra prometheus

FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS runtime

ARG TIMEZONE=Asia/Jakarta

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/opt/venv/bin:$PATH \
    TZ=${TIMEZONE} \
    HEALTH_HTTP_ENABLED=true \
    HEALTH_HTTP_HOST=127.0.0.1 \
    HEALTH_HTTP_PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    curl \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --no-create-home --gid app --shell /sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY app ./app

# Source stays root-owned; the app user only writes the generated .env and logs.
RUN chown app:app /app && install -d -o app -g app /app/logs

USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["/opt/venv/bin/python", "-m", "routemq.healthcheck"]

CMD ["/opt/venv/bin/routemq", "--run"]
