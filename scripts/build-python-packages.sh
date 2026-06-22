#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

npm --prefix packages/goodomics/dashboard ci
npm --prefix packages/goodomics/dashboard run build

uv run python -m build packages/goodomics
uv run python -m build packages/goodomics-full
