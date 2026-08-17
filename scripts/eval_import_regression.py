#!/usr/bin/env python3
"""KPI catégorie C du plan produit "mode admin d'import" (2026-08-17) :
vérifie qu'un import n'a pas dégradé le chatbot existant.

Principe : lance scripts/eval_retrieval.py::TEST_QUERIES avant ET après un
commit d'import, compare les intents/entités détectés et le classement des
résultats. Une baisse sur des requêtes qui fonctionnaient déjà doit bloquer
la validation de l'import (à câbler dans le dashboard admin, écran
import-preview -- ou en post-commit avec alerte si dégradation détectée).

Squelette uniquement -- réutilise scripts/eval_retrieval.py::TEST_QUERIES
et pipeline.retrieve(), logique de comparaison avant/après pas encore
écrite (dépend de la définition exacte de "dégradation" à trancher :
changement d'intent ? sortie du top-5 d'une source qui y était avant ?).

Usage prévu :
    python3 scripts/eval_import_regression.py --before results_before.json
    # ... import réalisé via le dashboard admin ...
    python3 scripts/eval_import_regression.py --after results_before.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
sys.path.insert(0, str(Path(__file__).parent))

from eval_retrieval import TEST_QUERIES  # noqa: E402


def capture_snapshot() -> dict:
    """Lance TEST_QUERIES et capture intent/top-5 entity_id par requête,
    pour comparaison ultérieure. Pas encore implémenté."""
    raise NotImplementedError


def compare_snapshots(before: dict, after: dict) -> list:
    """Retourne la liste des requêtes dont le comportement s'est dégradé
    (changement d'intent inattendu, source auparavant top-5 disparue).
    Pas encore implémenté."""
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit("Squelette de structure -- pas encore implémenté, voir docstring.")
