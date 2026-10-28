#!/usr/bin/env bash
# Starts the AutoJopps prototype (backend + built UI) on http://localhost:8000
set -e
cd "$(dirname "$0")/backend"
if [ -d .venv ]; then source .venv/bin/activate; fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
