"""Étape 4/9 — déduplique les entrées classées, à la fois contre le batch
importé lui-même et contre la base existante (Neo4j/Qdrant), pas seulement
contre l'ancien jeu de données connu au moment de l'écriture de ce fichier.

Réutilise le principe stable_id existant (hash normalisé de contenu, voir
notebooks/etl_lib/ontology.py::stable_id -- dupliqué ici plutôt qu'importé,
même règle que text_normalize.py) pour générer un identifiant déterministe :
deux imports du même contenu (même après reformulation mineure de casse/
espaces) doivent produire le même stable_id, donc être reconnus comme
doublons sans intervention humaine.

Squelette uniquement -- logique pas encore implémentée."""
from typing import Any, Dict, List

from .models import DuplicateMatch


def compute_stable_id(question: str, answer: str) -> str:
    """Miroir de ontology.py::stable_id -- même algorithme, dupliqué
    volontairement (frontière app/<->notebooks étanche)."""
    raise NotImplementedError


def find_duplicates(entries: List[Dict[str, Any]]) -> List[DuplicateMatch]:
    """Vérifie chaque entrée contre :
      1. les autres entrées du même batch (doublons internes au fichier uploadé)
      2. les entity_id déjà présents dans Neo4j/Qdrant (doublons vs base existante)
    Ne supprime rien ici -- alimente juste PreviewResult.duplicates pour
    décision admin (le commit peut choisir de les ignorer ou de merger)."""
    raise NotImplementedError
