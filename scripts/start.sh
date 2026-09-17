#!/bin/sh
# Container entrypoint.
# Runs as root only long enough to make /app/data writable by the "glad" user
# (bind mounts created by older root-only images belong to root), then re-executes
# itself unprivileged. Running the container with `user:` skips that step.
set -e

DATA_DIR="${DATA_DIR:-/app/data}"

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR"
  if [ "$(stat -c %u "$DATA_DIR")" != "$(id -u glad)" ]; then
    echo "Fixing ownership of $DATA_DIR for the glad user..."
    chown -R glad:glad "$DATA_DIR"
  fi
  exec setpriv --reuid=glad --regid=glad --init-groups "$0" "$@"
fi

echo "Starting application setup as $(id -un)..."
echo

echo "Applying database migrations..."
python manage.py migrate --noinput
echo

echo "Importing initial data..."
python manage.py loaddata finance/fixtures/*.yaml
echo

echo "Starting server..."
# shellcheck disable=SC2086 # UVICORN_OPTIONS is intentionally word-split
exec uvicorn --host 0.0.0.0 --port 8000 ${UVICORN_OPTIONS} glad.asgi:application
