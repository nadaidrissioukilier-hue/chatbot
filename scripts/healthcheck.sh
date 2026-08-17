#!/usr/bin/env bash
# Vérification rapide de l'état global VM2. Sortie non-zéro si dégradé.
set -uo pipefail
source /opt/entraide/app/.env 2>/dev/null || source app/.env 2>/dev/null || true

FAIL=0

check() {
    local name="$1" cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "✓ $name"
    else
        echo "✗ $name"
        FAIL=1
    fi
}

check "Neo4j (bolt)"   "docker exec entraide-vm2-neo4j cypher-shell -u \"${NEO4J_USER:-neo4j}\" -p \"$NEO4J_PASSWORD\" 'RETURN 1'"
check "Qdrant"         "curl -sf http://127.0.0.1:6333/collections"
check "Redis"          "docker exec entraide-vm2-redis redis-cli ping | grep -q PONG"
check "API FastAPI"    "curl -sf http://127.0.0.1:${API_PORT:-8000}/health"

if [ "$FAIL" -eq 0 ]; then
    echo "✅ Tous les services sont sains"
else
    echo "⚠ Au moins un service est en échec — voir ci-dessus"
fi
exit $FAIL
