#!/bin/bash
# Authors' packing script: assemble the four Zenodo archives from the campaign directories.
# Reviewers do not need this; tools/fetch_data.sh downloads what it produces.
#
#   bash tools/pack_zenodo.sh <staging dir with the raw layout> <output dir>
#
# Layout inside the archives (what tools/fetch_data.sh unpacks into raw/):
#   openpilot/                  clean rerun store (jobs_clean.jsonl, results/*.results.jsonl, traces_*/, mutants/, suite + screen json)
#   openpilot_screen/           screening campaign (candidates, jobs_screen*, results/, traces_screen*/, traces_screentwin/)
#   transfuser/                 store (+ nominal/ = Proxima nominal runs r0-4 used as the first five baseline runs)
#   realfaults/pylot, realfaults/tfpp     jobs + results, Leaderboard records, traces, version trees and patches
set -euo pipefail
ST="${1:?staging dir}"; OUT="${2:?output dir}"; mkdir -p "$OUT"
pack() {  # name, then rsync-style includes relative to $ST
  local name=$1; shift
  local tmp="$OUT/_$name"; rm -rf "$tmp"; mkdir -p "$tmp"
  for rel in "$@"; do
    mkdir -p "$tmp/$(dirname "$rel")"
    cp -rL "$ST/$rel" "$tmp/$rel"
  done
  ( cd "$tmp" && zip -q -r "$OUT/satrp_raw_$name.zip" . ) && rm -rf "$tmp"
  echo "$(sha256sum "$OUT/satrp_raw_$name.zip" | cut -c1-64)  satrp_raw_$name.zip  $(du -h "$OUT/satrp_raw_$name.zip" | cut -f1)"
}
pack openpilot openpilot
pack openpilot_screening openpilot_screen
pack transfuser transfuser
# real faults: Leaderboard records without the per-run stdout logs (*.pylot.log, ~22 GB) and profiler dumps (*.profile.json, ~6 GB)
tmp="$OUT/_realfaults"; rm -rf "$tmp"; mkdir -p "$tmp/realfaults"
cp -rL "$ST/realfaults/tfpp" "$tmp/realfaults/tfpp"
mkdir -p "$tmp/realfaults/pylot"; cp -L "$ST"/realfaults/pylot/*.jsonl "$tmp/realfaults/pylot/"; cp -rL "$ST/realfaults/pylot/versions" "$tmp/realfaults/pylot/versions"
for d in "$ST"/realfaults/pylot/lb_results_*; do
  [ -d "$d" ] || continue; b=$(basename "$d"); mkdir -p "$tmp/realfaults/pylot/$b"
  ( cd "$d" && find . -type f \( -name "*.json" -o -name "*.json.log" -o -name "*.xml" -o -name "*.csv" -o -name "*.conf" \) ! -name "*.profile.json" -print0 | cpio -0 -pdm --quiet "$tmp/realfaults/pylot/$b" )
done
for d in versions_dt conf docs models_fix; do [ -e "$ST/realfaults/pylot/$d" ] && cp -rL "$ST/realfaults/pylot/$d" "$tmp/realfaults/pylot/$d"; done
( cd "$tmp" && zip -q -r "$OUT/satrp_raw_realfaults.zip" . ) && rm -rf "$tmp"
echo "$(sha256sum "$OUT/satrp_raw_realfaults.zip" | cut -c1-64)  satrp_raw_realfaults.zip  $(du -h "$OUT/satrp_raw_realfaults.zip" | cut -f1)"
