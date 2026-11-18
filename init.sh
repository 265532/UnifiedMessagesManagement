#!/bin/sh
set -e

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  PYTHON=python
fi

"$PYTHON" .harness/scripts/harness.py bootstrap
"$PYTHON" .harness/scripts/harness.py doctor
"$PYTHON" .harness/scripts/harness.py status
