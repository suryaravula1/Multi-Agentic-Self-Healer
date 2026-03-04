#!/usr/bin/env bash
# Download LogHub Linux sample logs for parser/diagnostician evaluation.
# Source: https://github.com/logpai/loghub (ISSRE'23, free for research)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/fixtures/loghub"
BASE_URL="https://raw.githubusercontent.com/logpai/loghub/master/Linux"

mkdir -p "$OUT"

for file in Linux_2k.log Linux_2k.log_structured.csv Linux_2k.log_templates.csv README.md; do
  echo "Fetching $file ..."
  curl -fsSL "$BASE_URL/$file" -o "$OUT/$file"
done

echo ""
echo "Done. Sample logs at: $OUT/Linux_2k.log"
echo "Run benchmark: python scripts/benchmark_logs.py"
