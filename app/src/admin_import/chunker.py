"""Étape 5/9 — découpe chaque entrée dédupliquée en chunks pour
l'embedding, même convention que le pipeline d'ingestion initial (voir
notebooks/02_Chunk.ipynb et scripts/_migrate_notebooks_for_faq_extra.py) :
un chunk "question seule" (matching question-à-question) + un chunk
"question+réponse" (matching question-à-contenu). Dupliqué ici plutôt
qu'importé depuis notebooks/etl_lib (frontière app/<->notebooks étanche).

Squelette uniquement -- logique pas encore implémentée."""
from typing import Any, Dict, List


def make_chunks(entry: Dict[str, Any], family: str) -> List[Dict[str, Any]]:
    """Retourne 1-2 chunks selon la famille :
      - "service" / "generic_faq" : 2 chunks (question seule, question+réponse)
      - "institution_profile" : 1 chunk (profil), rattaché à l'entity_id de
        l'Institution (existante ou nouvellement créée)
    Chaque chunk porte les métadonnées extraites (population_cible,
    institutions) pour que fusion_ranker.py puisse les exploiter sans
    changement côté ranking."""
    raise NotImplementedError
