"""Étape 6/9 — embedding incrémental des nouveaux chunks uniquement (jamais
de ré-encodage complet de la collection).

Reprend la logique de scripts/embed_incremental.py ("Ré-embed
data/chunks/chunks_all.jsonl -> data/embeddings/embeddings_all.jsonl SANS
ré-encoder les chunks deja embeddes"), rendue callable ici plutôt que
script CLI, pour être appelée depuis pipeline.py avec les chunks d'un job
précis (pas tout le corpus).

Squelette uniquement -- logique pas encore implémentée."""
from typing import Any, Dict, List


def embed_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """BGE-M3 (même modèle que l'ingestion initiale, voir config.py
    EMBEDDING_MODEL) sur CPU -- prévoir le même effet de "warmup" que lors
    de l'ingestion initiale (~58s sur le premier batch de 32 textes avant
    stabilisation du débit, voir docs/RESULTS.md) : ne pas juger la
    progression sur les premières secondes lors de l'affichage temps réel
    côté frontend/admin/views/import-pipeline.js."""
    raise NotImplementedError
