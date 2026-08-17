"""Étape 9/9 — vérifie la cohérence Neo4j<->Qdrant après un import
incrémental, cible 100% (même objectif que le pipeline d'ingestion
initial, voir docs/RESULTS.md).

Réutilise la logique de scripts/verify_graph_qdrant_sync.py, rendue
callable et restreinte aux entity_id touchés par le job en cours (pas un
balayage complet de la base à chaque import, pour rester rapide).

Squelette uniquement -- logique pas encore implémentée."""
from typing import List


def verify_ids(entity_ids: List[str]) -> "VerificationResult":
    """Vérifie que chaque entity_id de la liste existe bien à la fois dans
    Neo4j et dans Qdrant. Alimente le KPI "Cohérence Neo4j<->Qdrant" du
    dashboard (catégorie B du plan produit du 2026-08-17)."""
    raise NotImplementedError


class VerificationResult:
    """Placeholder de type de retour -- à formaliser en Pydantic (voir
    models.py) une fois verify_ids() implémenté : coherent_count,
    missing_in_neo4j, missing_in_qdrant."""
    pass
