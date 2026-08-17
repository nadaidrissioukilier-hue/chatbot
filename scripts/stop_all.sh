#!/usr/bin/env bash
UNIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$UNIT_DIR"

# Tue par PID (fichier) ET par nom (filet de secours si le PID fichier est
# obsolète -- race condition connue entre stop/start rapprochés, voir
# .claude/skills/run-entraide-mvp/SKILL.md Gotchas), PUIS ATTEND la mort
# réelle des process avant de rendre la main. Sans cette attente,
# start_all.sh relance immédiatement et le nouveau llama-server échoue au
# bind ("couldn't bind HTTP server socket", port encore tenu par l'ancien
# process) -- bug réel qui a laissé tourner l'API sans LLM, trouvé en test
# le 2026-08-13 (start_all.sh annonçait "prêt" sans vérifier, voir aussi le
# fix correspondant dans start_all.sh).
[ -f logs/api.pid ] && kill "$(cat logs/api.pid)" 2>/dev/null
[ -f logs/llama.pid ] && kill "$(cat logs/llama.pid)" 2>/dev/null
pkill -f "python3 main.py" 2>/dev/null || true
pkill -f "llama-server" 2>/dev/null || true
rm -f logs/api.pid logs/llama.pid

for i in $(seq 1 30); do
    pgrep -f "python3 main.py|llama-server" >/dev/null 2>&1 || break
    sleep 1
done
if pgrep -f "python3 main.py|llama-server" >/dev/null 2>&1; then
    echo "⚠ Processus encore actifs après 30s, kill -9 en dernier recours :"
    pgrep -fa "python3 main.py|llama-server"
    pkill -9 -f "python3 main.py" 2>/dev/null || true
    pkill -9 -f "llama-server" 2>/dev/null || true
fi

echo "API + llama.cpp arrêtés. Stockage toujours actif (docker compose -f infra/docker-compose.yml down pour l'arrêter aussi)."
