FROM python:3.15-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY app ./app

RUN uv pip install --system -e .

CMD ["routemq", "run"]
