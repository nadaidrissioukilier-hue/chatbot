"""Étape 7/9 — charge les entrées classées dans Neo4j de façon strictement
incrémentale.

Règle absolue : uniquement MERGE, jamais DETACH DELETE ni suppression de
nœuds existants -- contrairement à notebooks/05_Neo4j_Load.ipynb qui vide
toute la base à chaque exécution (adapté au rebuild complet, pas à un ajout
en live depuis le dashboard admin). Même principe de liens "signaux
confiants uniquement" déjà appliqué aux FAQ existantes (population/
institution extraits par règles, jamais de lien FAQ->Service inventé).

Réutilise le driver Neo4j déjà instancié ailleurs dans l'app (voir
tools/graph_search.py) plutôt que d'ouvrir une connexion séparée.

Squelette uniquement -- logique pas encore implémentée."""
from typing import Any, Dict, List, Tuple


def load_entries(entries: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """MERGE chaque entrée (FAQ ou enrichissement Institution selon sa
    famille). Retourne (entity_ids_created, entity_ids_updated) -- nécessaire
    pour permettre un rollback ciblé (voir models.py::ImportJob)."""
    raise NotImplementedError
