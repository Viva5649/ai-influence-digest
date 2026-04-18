#!/bin/bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <weekly_report.md> [output.png] [date_text]" >&2
  exit 1
fi

MD_PATH="$1"
DEFAULT_OUT="${MD_PATH%.md}.png"
OUT_PNG="${2:-$DEFAULT_OUT}"
DATE_TEXT="${3:-$(date +"%Y年%m月%d日")}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EXTRA_ARGS=()
[ -n "${AUTHOR_NAME:-}" ] && EXTRA_ARGS+=(--author-name "$AUTHOR_NAME")
AVATAR="${AVATAR_URL:-$SCRIPT_DIR/logo.jpg}"
[ -n "$AVATAR" ] && EXTRA_ARGS+=(--avatar-url "$AVATAR")

python3 "$SCRIPT_DIR/render_poster.py" \
  --md      "$MD_PATH" \
  --out     "$OUT_PNG" \
  --date    "$DATE_TEXT" \
  --poster-width 800 \
  "${EXTRA_ARGS[@]}"

echo "OK: $OUT_PNG"
