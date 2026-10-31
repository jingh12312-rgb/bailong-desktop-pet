#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(uname -s)" != Linux ]]; then
  printf '此启动器仅支持 Linux。\n' >&2
  exit 1
fi
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  BAILONG_PYTHON="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/../.venv/bin/python" ]]; then
  BAILONG_PYTHON="$ROOT/../.venv/bin/python"
else
  BAILONG_PYTHON="${BAILONG_PYTHON:-python3}"
fi
if [[ -d "$ROOT/tools/lib" ]]; then
  export LD_LIBRARY_PATH="$ROOT/tools/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
exec "$BAILONG_PYTHON" "$ROOT/app/pet.py" "$@"
