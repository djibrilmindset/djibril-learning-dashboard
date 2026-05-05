#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# ADELLE BRIGHT DATA SCRAPER · Scraping universel dashboard
# Tous les agents utilisent ce script pour collecter les données
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIGHT_API="https://api.brightdata.com"
BRIGHT_TOKEN="${BRIGHT_DATA_API_KEY:-}"
ZONE="${BRIGHT_DATA_ZONE:-}"

# Load env
if [ -f ~/.env ]; then source ~/.env 2>/dev/null || true; fi
if [ -z "$BRIGHT_TOKEN" ]; then
  echo "ERROR: BRIGHT_DATA_API_KEY not set" >&2
  exit 1
fi

TYPE="serp"
QUERY=""
LIMIT=10
OUTPUT=""

usage() {
  echo "Usage: $0 --type=serp|unlock|social --query=\"...\" [--limit=10] [--output=file.json]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --type=*) TYPE="${1#*=}" ;;
    --query=*) QUERY="${1#*=}" ;;
    --limit=*) LIMIT="${1#*=}" ;;
    --output=*) OUTPUT="${1#*=}" ;;
    *) usage ;;
  esac
  shift
done

[ -z "$QUERY" ] && usage

case "$TYPE" in
  serp)
    # SERP search via Bright Data
    curl -s -H "Authorization: Bearer $BRIGHT_TOKEN" \
      -H "Content-Type: application/json" \
      "$BRIGHT_API/serp/search?q=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$QUERY")&limit=$LIMIT" \
      | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(json.dumps({'results': [{'title': r.get('title',''), 'url': r.get('link',''), 'description': r.get('snippet','')} for r in d.get('organic',[])]}))"
    ;;

  unlock)
    # Unlock any URL via residential proxy
    curl -s -H "Authorization: Bearer $BRIGHT_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"url\": \"$QUERY\"}" \
      "$BRIGHT_API/webunlocker/unlock"
    ;;

  social)
    # Social media scraping
    curl -s -H "Authorization: Bearer $BRIGHT_TOKEN" \
      -H "Content-Type: application/json" \
      "$BRIGHT_API/datasets/trigger?dataset_id=$QUERY&limit=$LIMIT"
    ;;

  *)
    echo "Unknown type: $TYPE" >&2
    exit 1
    ;;
esac

if [ -n "$OUTPUT" ]; then
  mv /tmp/bright_result.json "$OUTPUT" 2>/dev/null || true
fi
