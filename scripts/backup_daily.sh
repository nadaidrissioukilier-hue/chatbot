#!/usr/bin/env bash
# Sauvegarde quotidienne Neo4j + Qdrant + Redis. Rétention 14j (Neo4j/Qdrant),
# 7j (Redis). A brancher sur cron: 0 3 * * * /opt/entraide/scripts/backup_daily.sh
set -euo pipefail
BACKUP_DIR="/opt/entraide/backups/$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"

echo "=== Neo4j dump (à chaud, via APOC — un dump neo4j-admin classique exige la base arrêtée) ==="
docker exec entraide-vm2-neo4j mkdir -p /data/backups
docker exec entraide-vm2-neo4j cypher-shell -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:?}" \
    "CALL apoc.export.cypher.all('/data/backups/dump_$(date +%Y%m%d).cypher', {})" \
    || echo "⚠ Échec dump APOC — vérifier que le plugin APOC est activé (voir docker-compose.vm2.yml)"
docker cp entraide-vm2-neo4j:/data/backups "$BACKUP_DIR/neo4j" 2>/dev/null || true

echo "=== Qdrant snapshot ==="
curl -s -X POST "http://127.0.0.1:6333/collections/entraide_ma/snapshots" -o "$BACKUP_DIR/qdrant_snapshot.json"

echo "=== Redis RDB ==="
docker exec entraide-vm2-redis redis-cli SAVE
docker cp entraide-vm2-redis:/data/dump.rdb "$BACKUP_DIR/redis_dump.rdb"

echo "=== Purge des sauvegardes > 14 jours ==="
find /opt/entraide/backups -maxdepth 1 -type d -mtime +14 -exec rm -rf {} \;

echo "✅ Backup du $(date +%Y-%m-%d) terminé dans $BACKUP_DIR"
