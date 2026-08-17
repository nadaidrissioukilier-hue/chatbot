"""Contrats de données du pipeline d'import admin.

Ce fichier définit la forme des objets échangés entre les étapes et exposés
par admin_import_routes.py — c'est le contrat stable, indépendant de
l'implémentation de chaque étape (encore à écrire, voir les autres modules
de ce package)."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ImportStage(str, Enum):
    """Les 9 étapes du pipeline, dans l'ordre — utilisé pour la vue
    "pipeline visuel" du dashboard (statut par étape en direct)."""
    UPLOADED = "uploaded"
    SHAPE_NORMALIZED = "shape_normalized"
    FIELDS_MAPPED = "fields_mapped"
    CLASSIFIED = "classified"
    DEDUPLICATED = "deduplicated"
    CHUNKED = "chunked"
    EMBEDDED = "embedded"
    LOADED_NEO4J = "loaded_neo4j"
    INDEXED_QDRANT = "indexed_qdrant"
    VERIFIED = "verified"
    FAILED = "failed"


class FieldMapping(BaseModel):
    """Correspondance entre les noms de champs réels du JSON uploadé et le
    schéma cible interne. Proposée automatiquement (heuristique puis LLM si
    ambigu) et modifiable par l'admin avant validation."""
    question_field: str
    answer_field: str
    category_field: Optional[str] = None
    metadata_fields: List[str] = []
    confidence: float  # 0-1 ; sous un seuil, l'UI force une confirmation manuelle
    source: str  # "heuristic" | "llm_suggested" | "manual_override"


class ClassificationRuleMatch(BaseModel):
    entry_index: int
    family: str  # nom de règle depuis classification_rules.json, ou "generic_faq"
    matched_fields: List[str]


class DuplicateMatch(BaseModel):
    entry_index: int
    existing_entity_id: str
    similarity: float


class PreviewResult(BaseModel):
    """Résultat du dry-run (GET /admin/import/{id}/preview) — jamais
    d'écriture Neo4j/Qdrant à ce stade, uniquement pour validation humaine."""
    job_id: str
    total_entries: int
    field_mapping: FieldMapping
    family_counts: Dict[str, int]  # ex: {"service": 12, "institution": 3, "generic_faq": 5}
    duplicates: List[DuplicateMatch]
    unclassified_count: int  # devrait toujours être 0 (fallback generic_faq garanti)
    warnings: List[str]


class ImportJob(BaseModel):
    """État persistant d'un job d'import, stocké dans Redis (voir
    job_store.py) et exposé par GET /admin/import/{id}/status."""
    job_id: str
    filename: str
    uploaded_by: str  # admin username
    created_at: str  # ISO 8601
    stage: ImportStage
    stage_counts: Dict[str, int] = {}  # compteurs d'items par étape traversée
    error: Optional[str] = None
    preview: Optional[PreviewResult] = None
    committed: bool = False
    entity_ids_created: List[str] = []  # nécessaire pour un rollback ciblé
    entity_ids_updated: List[str] = []


class ImportCommitRequest(BaseModel):
    job_id: str
    field_mapping_override: Optional[FieldMapping] = None  # si l'admin corrige le mapping proposé


class ImportRollbackResult(BaseModel):
    job_id: str
    entities_removed: int
    entities_reverted: int
