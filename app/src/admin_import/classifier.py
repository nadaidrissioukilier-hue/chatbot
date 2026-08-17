"""Étape 3/9 — classe chaque entrée mappée (voir field_mapper.py) selon les
règles de classification_rules.json.

Garde-fou non négociable : toute entrée qui ne matche aucune règle explicite
tombe dans la règle "generic_faq" (is_fallback=true) -- jamais de rejet
silencieux. Vérifié par un assert de conservation du total, sur le même
principe que scripts/normalize_faq_dataset.py::main() (assert que
famille_A + famille_B + famille_C == total_input).

Squelette uniquement -- logique pas encore implémentée."""
import json
from pathlib import Path
from typing import Any, Dict, List

from .models import ClassificationRuleMatch

RULES_PATH = Path(__file__).parent / "classification_rules.json"


def load_rules() -> Dict[str, Any]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def classify_entries(entries: List[Dict[str, Any]]) -> List[ClassificationRuleMatch]:
    """Pour chaque entrée mappée, retourne la première règle dont un des
    groupes required_fields_any_of est entièrement présent ; sinon la règle
    marquée is_fallback=true. Longueur du résultat == longueur de `entries`,
    toujours (contrat testé par test_classifier.py, à écrire)."""
    raise NotImplementedError
