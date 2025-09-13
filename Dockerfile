FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock* ./
COPY . .
RUN uv sync

RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

USER app
RUN uv run python -c "import sys; sys.exit(0)"

CMD ["uv", "run", "python", "main.py", "--run"]

