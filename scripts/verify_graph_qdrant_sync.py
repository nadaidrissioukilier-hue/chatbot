#!/usr/bin/env python3
"""Vérifie la cohérence des IDs entre Neo4j et Qdrant — cible du guide: 100%.

C'est précisément le contrôle qui manquait dans la v1 et qui aurait révélé
le bug de seed-ID entre vector_search et graph_search avant la mise en prod.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from src.config import (
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION,
)


def neo4j_ids(driver) -> set:
    ids = set()
    with driver.session() as session:
        for label in ("Centre", "Service", "Programme", "FAQ"):
            for r in session.run(f"MATCH (n:{label}) RETURN n.id AS id"):
                ids.add(r["id"])
    return ids


def qdrant_entity_ids(client: QdrantClient) -> set:
    ids = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=QDRANT_COLLECTION, limit=1000, offset=offset,
            with_payload=["entity_id"], with_vectors=False,
        )
        ids.update(p.payload.get("entity_id") for p in points if p.payload.get("entity_id"))
        if offset is None:
            break
    return ids


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    n_ids = neo4j_ids(driver)
    q_ids = qdrant_entity_ids(client)

    only_neo4j = n_ids - q_ids
    only_qdrant = q_ids - n_ids
    common = n_ids & q_ids

    print(f"IDs Neo4j (Centre/Service/Programme/FAQ) : {len(n_ids)}")
    print(f"IDs Qdrant (entity_id distincts)          : {len(q_ids)}")
    print(f"IDs communs                                : {len(common)}")
    coherence = 100 * len(common) / max(len(n_ids), 1)
    print(f"\nCohérence Neo4j -> Qdrant : {coherence:.1f}% (cible guide : 100%)")

    if only_neo4j:
        print(f"\n⚠ {len(only_neo4j)} IDs présents dans Neo4j mais absents de Qdrant (non trouvables par le chatbot)")
        print(f"  exemples: {list(only_neo4j)[:5]}")
    if only_qdrant:
        print(f"\n⚠ {len(only_qdrant)} IDs présents dans Qdrant mais absents de Neo4j (pas d'expansion graphe possible)")
        print(f"  exemples: {list(only_qdrant)[:5]}")

    driver.close()
    sys.exit(0 if coherence >= 99.0 else 1)


if __name__ == "__main__":
    main()
