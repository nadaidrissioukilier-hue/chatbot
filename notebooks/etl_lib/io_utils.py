"""Utilitaires d'E/S robustes — lecture JSON/JSONL avec réparation, écriture.

centres.jsonl est explicitement documenté comme bruité (lignes cassées,
champs décalés) : toute lecture doit tolérer et compter les erreurs plutôt
que de faire planter tout le pipeline sur une ligne invalide.
"""
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


def load_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def stream_jsonl_repair(path: Path) -> Iterator[Dict]:
    """Lit un .jsonl ligne par ligne, ignore silencieusement les lignes
    invalides (tente une réparation légère avant d'abandonner). Ne lève
    jamais d'exception sur des données sales."""
    if not path.exists():
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
                continue
            except json.JSONDecodeError:
                pass
            # Réparation légère : troncature sur la dernière accolade fermante
            repaired = line[: line.rfind("}") + 1] if "}" in line else None
            if repaired:
                try:
                    yield json.loads(repaired)
                except json.JSONDecodeError:
                    pass


def save_jsonl(path: Path, records: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> List[Dict]:
    return list(stream_jsonl_repair(path))
