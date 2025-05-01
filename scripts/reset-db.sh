#!/bin/bash

set -e

python_path="$1"

echo "Remove old database and migrations"
rm -fv data/glad.db
rm -fv */migrations/00*.py
echo
echo "Recreate database and apply migrations"
$python_path manage.py makemigrations
$python_path manage.py migrate
echo
echo "Create superuser"
$python_path manage.py createsuperuser --noinput
echo
echo "Load initial data"
$python_path manage.py loaddata finance/fixtures/*.yaml
$python_path manage.py loaddata tests/fixtures/*.yaml
echo "Database reset complete."
