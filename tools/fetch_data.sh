#!/bin/bash
# Download and unpack the raw benchmark record (Zenodo) into raw/ so that the instances in
# data/derived/ can be rebuilt from scratch (python3 satrp/adapter.py; python3 realfaults/analysis/real_numbers.py).
# The shipped data/derived/ files already allow every paper number to be recomputed without this step.
#
#   bash tools/fetch_data.sh                 # all four archives (~2.5 GB)
#   bash tools/fetch_data.sh openpilot       # one archive: openpilot | transfuser | realfaults | openpilot_first_campaign
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZENODO_RECORD="${ZENODO_RECORD:-<ZENODO-RECORD-ID>}"      # TODO: set once the record is published
BASE="https://zenodo.org/records/${ZENODO_RECORD}/files"
ARCHIVES="${*:-openpilot transfuser realfaults openpilot_first_campaign}"
mkdir -p "$ROOT/raw"; cd "$ROOT/raw"
for a in $ARCHIVES; do
  f="satrp_raw_${a}.zip"
  [ -f "$f" ] || curl -L -o "$f" "$BASE/$f?download=1"
  sha=$(grep -E "^[0-9a-f]{64}  $f$" "$ROOT/docs/DATA.md" | awk '{print $1}' | head -1)
  if [ -n "$sha" ]; then echo "$sha  $f" | sha256sum -c - ; fi
  unzip -q -o "$f"
done
echo "unpacked into $ROOT/raw:"; ls "$ROOT/raw"
