#!/bin/sh
set -e

echo "Starting application setup..."
echo

echo "Applying database migrations..."
python manage.py migrate
echo

echo "Importing initial data..."
python manage.py loaddata finance/fixtures/*.yaml
echo

echo "Collect static files..."
python manage.py collectstatic --noinput
echo

echo "Starting server..."
exec uv run uvicorn --host 0.0.0.0 --port 8000 glad.asgi:application
