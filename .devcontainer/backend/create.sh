#!/bin/bash

set -e

curl -LsSf https://astral.sh/uv/install.sh | sh

cd /workspace/backend
uv sync --frozen
uv run pre-commit install
