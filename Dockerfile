# Runs the CLI in demo mode by default; pass env vars for live mode.
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev

COPY fixtures ./fixtures
COPY evals ./evals
COPY profile.example.md ./

ENV PATH="/app/.venv/bin:$PATH" DEMO_MODE=true DB_PATH=/data/jobs.sqlite
VOLUME ["/data"]

ENTRYPOINT ["eu-jobs"]
CMD ["--help"]
