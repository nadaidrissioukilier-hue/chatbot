"""Orchestrateur du pipeline d'import admin -- assemble les 9 étapes dans
l'ordre, met à jour job_store après chacune (pour le polling temps réel),
et sépare strictement la phase "preview" (aucune écriture) de la phase
"commit" (écriture réelle), conformément au plan produit du 2026-08-17.

Miroir de retrieval/pipeline.py dans son rôle (assembler les étapes), mais
pour le chemin d'écriture plutôt que de lecture.

Squelette uniquement -- logique pas encore implémentée."""
from typing import Any, Dict

from .models import ImportJob, PreviewResult
from . import shape_normalizer, field_mapper, classifier, deduplicator
from . import chunker, embedder, neo4j_loader, qdrant_indexer, verifier
from . import job_store


def run_preview(job_id: str, raw_json: Any) -> PreviewResult:
    """Étapes 1-4 uniquement (shape -> mapping -> classification -> dédup).
    Aucune écriture Neo4j/Qdrant. Résultat affiché à l'admin avant toute
    décision de /commit."""
    raise NotImplementedError


def run_commit(job_id: str, field_mapping_override: Dict[str, Any] = None) -> ImportJob:
    """Reprend depuis le résultat de preview (ou refait le mapping si
    field_mapping_override fourni), puis exécute les étapes 5-9
    (chunk -> embed -> neo4j -> qdrant -> verify). Écrit entity_ids_created/
    entity_ids_updated sur le job pour permettre un rollback ciblé ensuite."""
    raise NotImplementedError


def run_rollback(job_id: str) -> "ImportRollbackResult":
    """Supprime uniquement les entity_id créés par ce job précis (jamais un
    wipe global) -- utilise ImportJob.entity_ids_created/entity_ids_updated
    enregistrés lors du commit."""
    raise NotImplementedError
