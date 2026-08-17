"""Vectoriseur sparse partagé (indexation ET requête doivent utiliser exactement
le même vectoriseur, sinon le score sparse n'a pas de sens).

La v1 simulait le sparse search avec un vecteur nul contre une collection qui
n'existait pas (bug corrigé ici, voir audit). On implémente un TF-IDF hashé
léger — pas de dépendance lourde supplémentaire, déterministe, et suffisant
pour un corpus de quelques milliers de chunks bilingues AR/FR.
"""
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

VOCAB_SIZE = 2**18  # espace de hachage (réduit les collisions à un niveau négligeable)

_AR_DIACRITICS = re.compile(r"[ؗ-ًؚ-ْٰۖ-ۭ]")
_TOKEN_RE = re.compile(r"[\w؀-ۿ]+", re.UNICODE)


def normalize_text(text: str) -> str:
    """Normalisation légère AR+FR: diacritiques, alif/ya/ta marbouta, casse."""
    if not text:
        return ""
    text = _AR_DIACRITICS.sub("", text)
    text = text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا")  # إأآ -> ا
    text = text.replace("ى", "ي")  # ى -> ي
    text = text.replace("ة", "ه")  # ة -> ه
    return text.lower().strip()


def tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(normalize_text(text))


def _hash_token(token: str) -> int:
    return hash(token) % VOCAB_SIZE


def term_frequencies(text: str) -> Counter:
    return Counter(_hash_token(t) for t in tokenize(text))


class SparseVectorizer:
    """TF-IDF hashé. `idf` doit être calculé une fois sur tout le corpus à
    l'indexation (scripts/load_qdrant.py) puis persisté et rechargé tel quel
    au moment de la requête (app/src/tools/vector_search.py)."""

    def __init__(self, idf: Dict[str, float] = None):
        self.idf: Dict[int, float] = {int(k): v for k, v in (idf or {}).items()}

    @staticmethod
    def fit_idf(texts: List[str]) -> Dict[int, float]:
        n_docs = len(texts)
        doc_freq = Counter()
        for text in texts:
            for token_hash in set(_hash_token(t) for t in tokenize(text)):
                doc_freq[token_hash] += 1
        return {h: math.log((n_docs + 1) / (df + 1)) + 1.0 for h, df in doc_freq.items()}

    def vectorize(self, text: str) -> Tuple[List[int], List[float]]:
        tf = term_frequencies(text)
        if not tf:
            return [], []
        indices, values = [], []
        for token_hash, freq in tf.items():
            idf = self.idf.get(token_hash, 1.0)
            indices.append(token_hash)
            values.append(float(freq) * idf)
        # Qdrant exige des indices triés pour un stockage/scoring optimal
        order = sorted(range(len(indices)), key=lambda i: indices[i])
        return [indices[i] for i in order], [values[i] for i in order]

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.idf), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "SparseVectorizer":
        if not path.exists():
            return cls({})
        return cls(json.loads(path.read_text(encoding="utf-8")))
