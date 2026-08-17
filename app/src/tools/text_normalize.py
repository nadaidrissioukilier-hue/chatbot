"""Query Preprocessor / Normalisation — premier maillon de l'architecture
(2026-08-13), avant Calculator/Router. Miroir exact de
notebooks/etl_lib/ontology.py:normalize_arabic() (pipeline d'ingestion),
volontairement dupliqué (pas d'import cross-arbre notebooks/<->app/) mais
byte-à-byte identique : sinon une requête avec hamza ("أين") ne matche pas
un chunk indexé avec la forme sans hamza ("اين"), bien que ce soit
sémantiquement identique -- normaliser la requête ET l'index de la même
façon est ce qui rend le matching robuste aux variantes d'écriture.

Utilisée pour le ROUTAGE (intent/entités), l'EMBEDDING (dense+sparse) et la
CLÉ DE CACHE Redis. Le texte ORIGINAL (non normalisé) reste celui envoyé au
LLM dans le prompt final (préserve la formulation exacte de l'usager)."""
import re
import unicodedata

_DIACRITICS_RE = re.compile(r"[ً-ٰٟ]")


def normalize_query(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _DIACRITICS_RE.sub("", text)
    text = text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي")
    text = text.replace("ة", "ه")
    text = text.replace("ـ", "")  # tatweel
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()
