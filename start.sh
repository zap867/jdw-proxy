#!/bin/sh
# Copyright (c) 2026 abdurrehmandaudi
# Required Notice: Copyright (c) 2026 abdurrehmandaudi -- justdowork-proxy
# Licensed under the PolyForm Noncommercial License 1.0.0 -- commercial
# use is not permitted without a separate written commercial license.
# See LICENSE or https://polyformproject.org/licenses/noncommercial/1.0.0
# ---------------------------------------------------------------------------
#  Start ccproxy on macOS / Linux.
#
#      sh start.sh
#
#  The first run creates a local .venv and installs flask + requests into it.
#  Nothing is installed globally, and nothing outside this folder is touched.
# ---------------------------------------------------------------------------
cd "$(dirname "$0")" || exit 1

if command -v uv >/dev/null 2>&1; then
  echo "[uv] Using uv environment manager..."
  if [ -z "$UPSTREAM_API_KEY" ] && grep -q '"api_key": ""' config.json 2>/dev/null; then
    echo "[-] Note: UPSTREAM_API_KEY is not set in environment or config.json."
    echo "    Running in Dynamic Pass-through mode (9Router / client will provide API keys per request)."
  fi
  echo
  echo "Starting ccproxy ... (the exact URL is printed on the next line)"
  echo "Press Ctrl+C to stop."
  echo
  exec uv run ccproxy.py
fi

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "!! Neither uv nor Python 3 was found."
  echo "   Install uv (recommended): curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "   or macOS: brew install python3"
  exit 1
fi

if [ ! -x ".venv/bin/python3" ]; then
  echo "Creating .venv (first run only, this takes a minute) ..."
  "$PY" -m venv .venv || exit 1
  ./.venv/bin/python3 -m pip install --quiet --upgrade pip || exit 1
  echo "Installing dependencies ..."
  ./.venv/bin/python3 -m pip install --quiet -r requirements.txt || exit 1
fi

if [ -z "$UPSTREAM_API_KEY" ] && grep -q '"api_key": ""' config.json 2>/dev/null; then
  echo "[-] Note: UPSTREAM_API_KEY is not set in environment or config.json."
  echo "    Running in Dynamic Pass-through mode (9Router / client will provide API keys per request)."
fi

echo
echo "Starting ccproxy ... (the exact URL is printed on the next line)"
echo "Press Ctrl+C to stop."
echo

exec ./.venv/bin/python3 ccproxy.py
