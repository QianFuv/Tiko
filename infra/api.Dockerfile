FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock .python-version ./

RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY tiko ./tiko

EXPOSE 8000

CMD [".venv/bin/uvicorn", "tiko.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
