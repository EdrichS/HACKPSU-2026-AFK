#!/usr/bin/env bash
# Builds a tiny speaker dataset from macOS text-to-speech voices so the pipeline
# can be tested without a human. Usage: scripts/make_synthetic_speakers.sh OUTDIR
set -euo pipefail
OUT="${1:?usage: $0 OUTDIR}"
VOICES=(Daniel Karen Moira Rishi Fred Kathy Ralph Albert)
SENTENCES=(
  "The quick brown fox jumps over the lazy dog while the sun sets slowly behind the distant mountains."
  "Please remember to bring your laptop charger and a water bottle to the hackathon tomorrow morning."
  "I think the weather this weekend will be perfect for a long hike along the river trail."
  "Our team spent the entire night debugging the audio pipeline before the final presentation."
)
for V in "${VOICES[@]}"; do
  mkdir -p "$OUT/$V"
  i=1
  for S in "${SENTENCES[@]}"; do
    say -v "$V" -o "$OUT/$V/s$i.wav" --data-format=LEI16@16000 "$S"
    i=$((i+1))
  done
  echo "made $OUT/$V (${#SENTENCES[@]} clips)"
done
