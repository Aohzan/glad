#!/bin/bash

set -e

python_path="$1"

echo "Remove old database and migrations"
rm -fv data/glad.db
rm -fv */migrations/00*.py
echo
$python_path manage.py makemigrations
$python_path manage.py migrate
$python_path manage.py createsuperuser --noinput
$python_path manage.py loaddata finance/fixtures/*.yaml
$python_path manage.py loaddata tests/fixtures/*.yaml
