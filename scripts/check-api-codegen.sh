#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repository_root}"
bash scripts/generate-api.sh
git diff --exit-code -- \
  openapi/goodomics.openapi.json \
  packages/goodomics/dashboard/src/api/generated
