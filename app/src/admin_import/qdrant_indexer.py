"""Étape 8/9 — indexe les embeddings dans Qdrant de façon strictement
incrémentale.

Règle absolue : upsert de points uniquement, jamais recreate_collection --
contrairement à notebooks/06_Qdrant_Index.ipynb qui recrée la collection à
chaque exécution (adapté au rebuild complet, pas à un ajout en live). Les
entity_id doivent rester les mêmes entre Neo4j et Qdrant (voir verifier.py)
-- même convention que scripts/load_qdrant.py.

Squelette uniquement -- logique pas encore implémentée."""
from typing import Any, Dict, List


def index_chunks(embedded_chunks: List[Dict[str, Any]]) -> int:
    """Upsert des points dense+sparse dans la collection existante
    (QDRANT_COLLECTION, voir config.py). Retourne le nombre de points
    upsertés."""
    raise NotImplementedError
