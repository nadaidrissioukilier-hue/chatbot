#!/usr/bin/env python3
"""Phase stockage — Qdrant : crée la collection unique `entraide_ma` avec
vecteurs nommés dense (BGE-M3, 1024, cosine) + sparse (TF-IDF hashé), et les
index payload pour le filtrage métier.

Corrige le bug v1 : deux collections séparées (une fausse) -> une seule
collection avec vecteurs nommés, cohérente avec le guide de déploiement.
Idempotent : peut être relancé sans risque (recrée la collection si demandé).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, PayloadSchemaType,
)

from src.config import (
    QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION,
    QDRANT_DENSE_VECTOR_NAME, QDRANT_SPARSE_VECTOR_NAME, EMBEDDING_DIM,
)

RECREATE = "--recreate" in sys.argv


def main():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    exists = client.collection_exists(QDRANT_COLLECTION)

    if exists and RECREATE:
        client.delete_collection(QDRANT_COLLECTION)
        exists = False
        print(f"  Collection existante supprimée: {QDRANT_COLLECTION}")

    if not exists:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config={
                QDRANT_DENSE_VECTOR_NAME: VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                QDRANT_SPARSE_VECTOR_NAME: SparseVectorParams(),
            },
        )
        print(f"✓ Collection créée: {QDRANT_COLLECTION} (dense={EMBEDDING_DIM}D cosine, sparse=hashé)")
    else:
        print(f"= Collection déjà présente: {QDRANT_COLLECTION} (utilisez --recreate pour repartir de zéro)")

    payload_indexes = {
        "entity_type": PayloadSchemaType.KEYWORD,
        "entity_id": PayloadSchemaType.KEYWORD,
        "chunk_type": PayloadSchemaType.KEYWORD,
        "population_cible": PayloadSchemaType.KEYWORD,
        "institutions": PayloadSchemaType.KEYWORD,
        "region": PayloadSchemaType.KEYWORD,
        "delegation": PayloadSchemaType.KEYWORD,
        "langue": PayloadSchemaType.KEYWORD,
        "is_eps": PayloadSchemaType.BOOL,
    }
    for field, schema in payload_indexes.items():
        client.create_payload_index(QDRANT_COLLECTION, field_name=field, field_schema=schema)
    print(f"✓ {len(payload_indexes)} index payload créés/vérifiés")

    info = client.get_collection(QDRANT_COLLECTION)
    print(f"✓ Points actuels dans la collection: {info.points_count}")


if __name__ == "__main__":
    main()
