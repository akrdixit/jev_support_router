#!/usr/bin/env bash
# Usage: ./run.sh        -> start the server at http://localhost:8010
#        ./run.sh test   -> run the tests
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d .venv ]; then
  echo "Creating virtualenv (needs Python 3.10+)..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env - add your TYPESAFE_API_KEY to it."
fi

if [ "$1" = "test" ]; then
  exec .venv/bin/pytest -q
fi

echo "Jev Support Router: http://localhost:8010  (API docs: /docs)"
exec .venv/bin/uvicorn app.main:app --port "${PORT:-8010}" --reload
