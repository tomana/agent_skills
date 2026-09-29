#!/usr/bin/env bash
# General headless image generation via the Codex CLI's image_generation tool
# (gpt-image on the ChatGPT subscription — NO API key). Needs the Codex CLI installed
# and logged in (`codex login`, auth_mode=chatgpt).
#
#   codex_img.sh OUT.png "PROMPT" [ref1.png ref2.png ...]
#
# Two rules baked in (see SKILL.md for why):
#   1. FORCE the image_generation tool — "do NOT write code" (else codex constructs
#      the image with flood-fill/mask CODE -> poor quality).
#   2. The PROMPT you pass decides displacement-map vs texture vs anything else.
# Reference images are passed by path; codex reads them from disk (it has file
# access under --dangerously-bypass-approvals-and-sandbox). Output lands in
# ~/.codex/generated_images/<uuid>/ and codex copies it to OUT.
set -euo pipefail
OUT="$1"; PROMPT="$2"; shift 2 || true
mkdir -p "$(dirname "$OUT")"; rm -f "$OUT"
REFS=""; for r in "$@"; do REFS="$REFS Reference image (open and read it): $r."; done
FULL="ONLY use your built-in image_generation tool to create ONE image. Do NOT write code, do NOT run any script, do NOT construct the image programmatically or with flood-fill/masks — generate it DIRECTLY with the image model, then save it as a PNG to exactly $OUT.
$PROMPT$REFS
Report the byte size of $OUT."
codex exec --dangerously-bypass-approvals-and-sandbox "$FULL" >/dev/null 2>&1
[ -s "$OUT" ] && echo "OK  $OUT  ($(stat -c%s "$OUT") bytes)" || { echo "FAIL $OUT"; exit 1; }
