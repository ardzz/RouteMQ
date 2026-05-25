ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /app

ARG TIMEZONE=Asia/Jakarta

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=${TIMEZONE}

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml README.md uv.lock* ./
COPY app ./app
COPY bootstrap ./bootstrap
COPY core ./core
COPY main.py ./

RUN if [ -f uv.lock ]; then uv sync --no-dev --frozen; else uv sync --no-dev; fi

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG TIMEZONE=Asia/Jakarta

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=${TIMEZONE}

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    curl \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml README.md ./
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/app ./app
COPY --from=builder /app/bootstrap ./bootstrap
COPY --from=builder /app/core ./core
COPY --from=builder /app/main.py ./

RUN groupadd --system app && useradd --system --no-create-home --gid app --shell /sbin/nologin app && \
    chown -R app:app /app

USER app

CMD ["uv", "run", "python", "main.py", "--run"]
