#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${1:-http://127.0.0.1:11441}"
curl --fail --silent --show-error "${BASE_URL}/health"
printf '\n'
curl --fail --silent --show-error "${BASE_URL}/ready"
printf '\n'
