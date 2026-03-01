FROM python:3.14-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install PostgreSQL client and build dependencies for psycopg
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        gcc \
        libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
# ADD --exclude=data . /app # TODO issue with github build
ADD . /app

RUN uv venv
ENV PATH="/app/.venv/bin:$PATH"

COPY uv.lock /app/uv.lock
RUN uv sync --frozen

CMD ["/app/scripts/start.sh"]
