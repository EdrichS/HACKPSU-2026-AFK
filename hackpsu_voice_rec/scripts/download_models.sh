#!/usr/bin/env bash
# Downloads the ONNX models used by voicerec into ./models
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p models
BASE_SPK="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models"  # (sic) typo is in the real tag
BASE_ASR="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"

fetch() {  # fetch <url> <dest>
  if [ -s "$2" ]; then echo "have  $2"; return; fi
  echo "fetch $2"; curl -sSL --fail -o "$2" "$1"
}

fetch "$BASE_ASR/silero_vad.onnx" models/silero_vad.onnx
fetch "$BASE_SPK/nemo_en_titanet_small.onnx" models/nemo_en_titanet_small.onnx
# speech-to-text for --transcribe (Moonshine base, English, ~250 MB download)
if [ ! -d models/sherpa-onnx-moonshine-base-en-int8 ]; then
  echo "fetch models/sherpa-onnx-moonshine-base-en-int8"
  curl -sSL --fail -o models/moonshine.tar.bz2 "$BASE_ASR/sherpa-onnx-moonshine-base-en-int8.tar.bz2"
  tar xjf models/moonshine.tar.bz2 -C models && rm models/moonshine.tar.bz2
else
  echo "have  models/sherpa-onnx-moonshine-base-en-int8"
fi
# voice for `voicerec assistant` (Supertonic 3, ~130 MB download)
if [ ! -d models/sherpa-onnx-supertonic-3-tts-int8-2026-05-11 ]; then
  echo "fetch models/sherpa-onnx-supertonic-3-tts-int8-2026-05-11"
  curl -sSL --fail -o models/supertonic.tar.bz2 "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/sherpa-onnx-supertonic-3-tts-int8-2026-05-11.tar.bz2"
  tar xjf models/supertonic.tar.bz2 -C models && rm models/supertonic.tar.bz2
else
  echo "have  models/sherpa-onnx-supertonic-3-tts-int8-2026-05-11"
fi
if [ "${1:-}" = "--all" ]; then
  fetch "$BASE_SPK/wespeaker_en_voxceleb_CAM%2B%2B.onnx" "models/wespeaker_en_voxceleb_CAM++.onnx"
fi
ls -la models
