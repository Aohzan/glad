# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.12.15

# ---------------------------------------------------------------------------
# Front-end vendor assets (Bootstrap, ApexCharts, Leaflet, ...)
# ---------------------------------------------------------------------------
FROM node:24-slim AS vendors
WORKDIR /app
COPY package.json package-lock.json ./
# postinstall (vendor-copy) populates static/vendors/
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

# ---------------------------------------------------------------------------
# Python virtual environment (runtime dependencies only)
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-trixie AS builder
ARG UV_VERSION
COPY --from=ghcr.io/astral-sh/uv:${UV_VERSION} /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

# ---------------------------------------------------------------------------
# Runtime image
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --system --gid 1000 glad \
    && useradd --system --uid 1000 --gid glad --home-dir /app --shell /usr/sbin/nologin glad

WORKDIR /app
COPY --chown=glad:glad . /app
COPY --from=builder --chown=glad:glad /app/.venv /app/.venv
COPY --from=vendors --chown=glad:glad /app/static/vendors /app/static/vendors

# Collect static files at build time (the runtime user cannot write to /app).
RUN SECRET_KEY=build-time-only DEBUG=false python manage.py collectstatic --noinput \
    && chown -R glad:glad /app/staticfiles \
    && mkdir -p /app/data && chown glad:glad /app/data \
    && chmod +x /app/scripts/start.sh

VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "/app/scripts/healthcheck.py"]

# start.sh fixes /app/data ownership then drops privileges to the glad user.
CMD ["/app/scripts/start.sh"]
