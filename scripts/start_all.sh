#!/usr/bin/env bash
# Démarre toute la stack MVP localhost : stockage (Docker) + llama.cpp
# (Qwen2.5-7B réel) + API FastAPI. Tout en arrière-plan, PIDs dans
# logs/*.pid pour stop_all.sh.
set -euo pipefail
UNIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$UNIT_DIR"
mkdir -p logs

echo "=== 1/3 Stockage (Neo4j/Qdrant/Redis) ==="
set -a; source app/.env; set +a
docker compose -f infra/docker-compose.yml up -d
storage_ready=false
for i in $(seq 1 30); do
    curl -sf "http://localhost:${QDRANT_PORT}/collections" >/dev/null 2>&1 && { storage_ready=true; break; }
    sleep 2
done
if [ "$storage_ready" != true ]; then
    echo "✗ Stockage (Qdrant) non joignable après 60s -- voir 'docker compose -f infra/docker-compose.yml logs'" >&2
    exit 1
fi
echo "✓ Stockage prêt"

echo "=== 2/3 llama.cpp (Qwen2.5-7B-Instruct) ==="
nohup ./scripts/start_llama.sh >logs/llama.log 2>&1 &
echo $! > logs/llama.pid
llama_ready=false
for i in $(seq 1 120); do
    curl -sf "http://localhost:28080/health" >/dev/null 2>&1 && { llama_ready=true; break; }
    sleep 2
done
if [ "$llama_ready" != true ]; then
    # 2026-08-13 : avant, ce script annonçait "prêt" ici même en échec (la
    # boucle épuisait juste ses itérations sans jamais vérifier le
    # résultat) -- bug réel qui a laissé tourner l'API sans LLM pendant
    # toute une session (RuntimeError "Connection refused" sur /chat côté
    # usager). Cause typique : relance trop rapide après stop_all.sh, le
    # port est encore tenu par l'ancien process ("couldn't bind HTTP server
    # socket" dans logs/llama.log) -- déjà mitigé par l'attente ajoutée dans
    # stop_all.sh, mais on vérifie ici plutôt que de supposer.
    echo "✗ llama.cpp non joignable après 240s -- voir logs/llama.log :" >&2
    tail -20 logs/llama.log >&2
    exit 1
fi
echo "✓ llama.cpp prêt (PID $(cat logs/llama.pid))"

echo "=== 3/3 API FastAPI ==="
source .venv/bin/activate
(cd app && nohup python3 main.py >../logs/api.log 2>&1 &)
sleep 2
API_PID=$(pgrep -f "python3 main.py" | head -1)
echo "$API_PID" > logs/api.pid
api_ready=false
for i in $(seq 1 60); do
    curl -sf "http://localhost:${API_PORT}/health" >/dev/null 2>&1 && { api_ready=true; break; }
    sleep 1
done
if [ "$api_ready" != true ]; then
    echo "✗ API FastAPI non joignable après 60s -- voir logs/api.log :" >&2
    tail -20 logs/api.log >&2
    exit 1
fi
echo "✓ API prête (PID $API_PID)"

echo ""
health_json=$(curl -sf "http://localhost:${API_PORT}/health")
echo "$health_json" | python3 -m json.tool
echo ""
# /health répond toujours HTTP 200 même dégradé (par design, voir main.py) --
# vérifier le corps explicitement plutôt que de se fier au seul code HTTP,
# sinon un service tombé entre l'étape 2/3 et maintenant passe inaperçu.
if echo "$health_json" | python3 -c "import sys,json; sys.exit(0 if json.load(sys.stdin).get('status')=='healthy' else 1)"; then
    echo "✅ Stack complète démarrée et saine. Logs dans logs/. Arrêt : scripts/stop_all.sh"
else
    echo "⚠ Stack démarrée mais DÉGRADÉE (voir le détail ci-dessus) -- ne pas considérer comme opérationnelle." >&2
    exit 1
fi
