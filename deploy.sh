#!/usr/bin/env bash
set -euo pipefail
# Manual build/publish entry point, run on the development machine or build worker.
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/scripts/publish-release.py" "$@"
