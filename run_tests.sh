#!/bin/sh
# Copyright (c) 2026 abdurrehmandaudi
# Required Notice: Copyright (c) 2026 abdurrehmandaudi -- justdowork-proxy
# Licensed under the PolyForm Noncommercial License 1.0.0 -- commercial
# use is not permitted without a separate written commercial license.
# See LICENSE or https://polyformproject.org/licenses/noncommercial/1.0.0
# Run ccproxy's offline tests. No real API key is needed -- the suite starts its
# own mock upstream.
cd "$(dirname "$0")" || exit 1

if command -v uv >/dev/null 2>&1; then
  exec uv run test_offline.py "$@"
fi

if [ ! -x ".venv/bin/python3" ]; then
  echo ".venv not found. Run start.sh once first -- it creates it."
  exit 1
fi

exec ./.venv/bin/python3 test_offline.py "$@"
