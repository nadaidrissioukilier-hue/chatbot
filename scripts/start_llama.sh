#!/usr/bin/env bash
# Démarre llama-server avec Qwen2.5-7B-Instruct Q4_K_M — paramètres alignés
# sur le guide (§3.3), threads limités volontairement (poste partagé, voir
# les leçons de cette session sur la contention CPU avec 04_Embed).
set -euo pipefail
UNIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL="$UNIT_DIR/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf"
BIN="/home/ubunto/llama.cpp/build/bin/llama-server"

if [ ! -f "$MODEL" ]; then
    echo "✗ Modèle introuvable : $MODEL (téléchargement pas encore terminé ?)" >&2
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
    --port 28080 \
    --parallel 2
