#!/usr/bin/env bash
# Regenerate every image and clip in docs/ and agensi/media/ from REAL runs of the three scripts in a two-device lab.
#   PLAYWRIGHT_DIR=/path/with/node_modules/playwright bash docs/media-src/make-media.sh
# Needs: Linux, root, iproute2 (ip), iptables, unshare, python3 with Pillow, ffmpeg, Node 20+ and Playwright with
# Chromium (PLAYWRIGHT_DIR is a folder whose node_modules has it, for example a scratch folder where you ran
# `npm install playwright`; set PLAYWRIGHT_BROWSERS_PATH too if the browsers are not in the default place).
# The lab is two network namespaces (dmd-laptop, dmd-desk) on a virtual cable. The host's own network is not touched.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/docs/media-src"
export ROOT PLAYWRIGHT_DIR="${PLAYWRIGHT_DIR:?set PLAYWRIGHT_DIR, see the header of this file}"
S="$ROOT/agensi/desk-mesh-doctor/scripts"
TMP="${MEDIA_TMP:-/tmp/dmd-media}"
rm -rf "$TMP" /tmp/dmd-demo /tmp/dmd-demo-blocked && mkdir -p "$TMP"
# shellcheck source=lab.sh
. "$SRC/lab.sh"

PIDS=()
start_lab() {   # a fresh lab: the desk drops inbound TCP 7001, and each device has a listener on 7001
  for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done
  PIDS=()
  lab_up
  for d in laptop desk; do
    nsrun "$d" python3 "$S/mesh_link.py" listen 7001 --seconds 300 --label "$d" >/dev/null 2>&1 </dev/null &
    PIDS+=($!)
  done
  sleep 1
}
trap 'for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; lab_down' EXIT

start_lab
python3 "$SRC/record.py" "$SRC/casts/verdict.json" "$TMP/verdict.cast.json"
node "$SRC/termcast.mjs" "$TMP/verdict.cast.json" "$TMP/verdict.png" --still
node "$SRC/fit-figure.mjs" "$TMP/fit.png" /tmp/dmd-demo-blocked "$S"
node "$SRC/social.mjs" "$TMP/social.png" "$TMP/verdict.cast.json" "$ROOT/agensi/media/logo.png"

start_lab
python3 "$SRC/record.py" "$SRC/casts/hero.json" "$TMP/hero.cast.json"
python3 "$SRC/transcript.py" "$TMP/hero.cast.json" "$ROOT/docs/demo-session.txt"
node "$SRC/termcast.mjs" "$TMP/hero.cast.json" "$ROOT/docs/demo.gif" "$ROOT/docs/demo.mp4"
node "$SRC/termcast.mjs" "$TMP/hero.cast.json" "$TMP/fixed.png" --still

python3 "$SRC/finish.py" "$TMP/fit.png" "$ROOT/docs/how-it-fits.png"
python3 "$SRC/finish.py" "$TMP/verdict.png" "$ROOT/docs/verdict.png"
python3 "$SRC/finish.py" "$TMP/social.png" "$ROOT/docs/social-preview.png" 0 0
cp "$ROOT/docs/how-it-fits.png" "$ROOT/agensi/media/screenshot-1.png"
python3 "$SRC/finish.py" "$TMP/verdict.png" "$ROOT/agensi/media/screenshot-2.png"
python3 "$SRC/finish.py" "$TMP/fixed.png" "$ROOT/agensi/media/screenshot-3.png"
ls -l "$ROOT"/docs/*.* "$ROOT"/agensi/media/*.png
