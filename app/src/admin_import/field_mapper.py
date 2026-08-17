"""Étape 2/9 — détecte quels champs de chaque entrée jouent le rôle
question/réponse/catégorie/métadonnées, sans connaître à l'avance les noms
réels utilisés par le JSON uploadé.

Trois niveaux, du plus rapide au plus robuste (voir plan produit du
2026-08-17) :
  1. heuristique par synonymes connus (question|q|query|سؤال|... /
     answer|a|reponse|réponse|جواب|إجابة|...), insensible à la casse/accents
  2. si ambigu (plusieurs champs candidats à confiance proche) ou si aucun
     candidat trouvé : soumettre 2-3 échantillons d'entrées au LLM local
     (llamacpp_client, déjà utilisé par app/src/inference/) et lui demander
     un FieldMapping structuré
  3. l'UI (frontend/admin/views/import-preview.js) affiche le mapping
     proposé + confidence, l'admin peut le corriger avant /commit
     (ImportCommitRequest.field_mapping_override)

Squelette uniquement -- logique pas encore implémentée."""
from typing import Any, Dict, List

from .models import FieldMapping

_QUESTION_SYNONYMS = ["question", "q", "query", "intitule", "intitulé", "سؤال"]
_ANSWER_SYNONYMS = ["answer", "a", "reponse", "réponse", "response", "جواب", "إجابة"]


def suggest_mapping_heuristic(sample_entries: List[Dict[str, Any]]) -> FieldMapping:
    """Tentative par correspondance de noms de champs (voir listes de
    synonymes ci-dessus). Retourne confidence basse si plusieurs champs
    candidats à égalité."""
    raise NotImplementedError


def suggest_mapping_llm(sample_entries: List[Dict[str, Any]]) -> FieldMapping:
    """Repli quand l'heuristique échoue ou est ambiguë -- utilise le LLM
    local déjà en place (pas d'appel externe) pour proposer un mapping.
    Toujours source="llm_suggested", jamais appliqué sans validation admin
    explicite si confidence < seuil (voir config.py)."""
    raise NotImplementedError


def apply_mapping(entries: List[Dict[str, Any]], mapping: FieldMapping) -> List[Dict[str, str]]:
    """Projette chaque entrée brute vers le schéma cible interne
    {"question": ..., "answer": ..., "category": ..., "metadata": {...}}."""
    raise NotImplementedError
