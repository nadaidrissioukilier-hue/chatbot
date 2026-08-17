"""Étape 1/9 — ramène n'importe quelle forme de JSON Q/R à une liste plate
de dict, avant toute détection de champs.

Formes à couvrir (voir docs/admin_import_schema.md) :
  - tableau plat déjà à la racine : [{...}, {...}]
  - objet racine avec une clé conteneur : {"faqs": [...]}, {"data": [...]}
    -> détecter automatiquement la première liste d'objets trouvée dans
    l'arbre plutôt que d'exiger un nom de clé précis
  - dict-de-dicts (clé = id, valeur = objet) -> convertir en liste, garder
    la clé comme candidat d'ID stable
  - JSONL (une entrée JSON par ligne) -> détecté par extension .jsonl ou par
    tentative de parse ligne-à-ligne si le parse JSON global échoue

Squelette uniquement -- structure du pipeline posée (2026-08-17), logique
pas encore implémentée. Ne PAS importer notebooks/etl_lib (frontière
app/<->notebooks volontairement étanche, voir tools/text_normalize.py)."""
from typing import Any, Dict, List


def detect_shape(raw: Any) -> str:
    """Retourne un identifiant de forme ("flat_list" | "container_object" |
    "dict_of_dicts" | "jsonl") pour traçabilité dans le rapport de preview."""
    raise NotImplementedError


def normalize_shape(raw: Any) -> List[Dict]:
    """Point d'entrée de l'étape : Any (JSON parsé) -> liste plate de dict.
    Ne doit jamais lever pour une forme inconnue -- au pire, remonter une
    liste vide + un warning consommé par PreviewResult.warnings."""
    raise NotImplementedError
