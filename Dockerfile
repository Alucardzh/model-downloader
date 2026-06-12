FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml ./
RUN uv sync --no-dev

COPY app/ app/
COPY static/ static/

EXPOSE 8000

CMD ["uv", "run", "model-download", "--host", "0.0.0.0", "--port", "8000"]
