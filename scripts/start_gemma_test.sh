#!/usr/bin/env bash
# Lancement de test pour Gemma 3 4B, sur un port SEPARE (28081) du Qwen2.5-7B
# de production (28080) -- comparaison cote a cote, sans toucher au service
# qui tourne (2026-08-14, demande "tester le modele de gemma").
set -euo pipefail
UNIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL="$UNIT_DIR/models/gemma/gemma-3-4b-it-Q4_K_M.gguf"
BIN="/home/ubunto/llama.cpp/build/bin/llama-server"

if [ ! -f "$MODEL" ]; then
    echo "✗ Modèle introuvable : $MODEL" >&2
    exit 1
fi
if [ ! -x "$BIN" ]; then
    echo "✗ llama-server introuvable : $BIN" >&2
    exit 1
fi

exec "$BIN" \
    -m "$MODEL" \
    -t 10 \
    -c 8192 \
    -ngl 0 \
    --temp 0.3 \
    --top-p 0.9 \
    --repeat-penalty 1.1 \
    -n 512 \
    --host 0.0.0.0 \
    --port 28081 \
    --parallel 2
