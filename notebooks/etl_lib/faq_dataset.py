"""Normalisation du dataset `data_faq` (129 FAQ enrichies, hors pipeline
d'origine du guide) -- voir analyse dans la conversation du 2026-08-12.

`faq_enriched.json` est la fusion deja enrichie (keywords+synonyms) des 8
autres fichiers du dossier (enfants/women/elderly/PSH/entraide_site/1/2/3) --
verifie par les comptes (13+12+11+22+17+16+16+22=129). Seul ce fichier est
lu ici, les 8 autres ne sont que ses sources.

Les 129 entrees ne sont PAS homogenes (62 schemas de `reponse` differents) --
elles se regroupent en 3 familles metier :
  A = FAQ Service (58, enfants/women/elderly/PSH) : memes champs que le
      Service existant (population/conditions/documents/institutions).
  B = Fiche Institution (institutions_1/2, acronyme+nom+cadre legal...) :
      CE N'EST PAS UNE FAQ, c'est de l'enrichissement de noeuds Institution
      deja/pas-encore dans INSTITUTION_MAP (CAS/EMF/SAMU_SOCIAL decouverts
      ici, voir ontology.py). institutions_1_X et institutions_2_X sont des
      doublons quasi-identiques du meme catalogue -- dedupliques par code.
  C = Contenu generique organisation/site (entraide_site + reste
      institutions_1/2/3) : mission/objectifs, pas d'entite precise a lier.
"""
from typing import Any, Dict, List, Tuple

from .ontology import clean_text, extract_institutions, match_population, stable_id

FAMILY_A_REQUIRED = {"شروط_الاستفادة", "الوثائق_المطلوبة"}
FAMILY_B_REQUIRED = {"الاختصار", "الاسم"}


def flatten_value(value: Any, depth: int = 0) -> str:
    """Aplati une valeur de `reponse` (str / liste / liste-de-dicts / dict
    imbrique) en texte lisible. Pas un json.dumps -- le LLM/l'embedding
    doivent recevoir du texte, pas de la syntaxe."""
    if value is None:
        return ""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [flatten_value(v, depth + 1) for v in value]
        return " | ".join(p for p in parts if p)
    if isinstance(value, dict):
        parts = [f"{k}: {flatten_value(v, depth + 1)}" for k, v in value.items() if v not in (None, "", [])]
        sep = " -- " if depth == 0 else ", "
        return sep.join(parts)
    return str(value)


def flatten_reponse(reponse: Dict) -> str:
    """Transforme le dict `reponse` (schema variable) en un texte plat unique,
    dans l'ordre des cles telles que fournies (deja un ordre metier logique
    dans la source: categorie -> axe -> services -> conditions -> documents)."""
    parts = []
    for key, value in reponse.items():
        flat = flatten_value(value)
        if flat:
            parts.append(f"{key.replace('_', ' ')}: {flat}")
    return ". ".join(parts)


def classify_family(reponse: Dict) -> str:
    keys = set(reponse.keys())
    if FAMILY_B_REQUIRED <= keys:
        return "B"
    if FAMILY_A_REQUIRED <= keys:
        return "A"
    return "C"


def normalize_faq_dataset(raw_faqs: List[Dict]) -> Tuple[List[Dict], List[Dict], List[Dict], Dict]:
    """Retourne (service_faqs, institution_enrichments, general_faqs, report).

    service_faqs / general_faqs partagent le meme schema (compatible avec le
    FAQ existant issu de faq_aos.jsonl: id/question_ar/reponse_ar) + des
    champs supplementaires (family, institutions, population_cible, keywords,
    synonyms) exploites par 02_Chunk / 05_Neo4j_Load.
    """
    service_faqs, institution_raw, general_faqs = [], [], []

    for f in raw_faqs:
        question = clean_text(f.get("question", ""))
        reponse = f.get("reponse", {}) or {}
        flat_text = flatten_reponse(reponse)
        family = classify_family(reponse)
        source_id = f.get("id", "")
        category = f.get("category", "")

        institutions, eps_fallback = extract_institutions(f"{question} {flat_text}")
        populations = match_population(f"{question} {flat_text}")

        record = {
            "id": stable_id("FAQX", category, question),
            "source_id": source_id,
            "category": category,
            "family": family,
            "question_ar": question,
            "reponse_ar": flat_text,
            "reponse_struct": reponse,
            "institutions": institutions,
            "eps_fallback": eps_fallback,
            "population_cible": populations,
            "keywords": f.get("keywords", []),
            "synonyms": f.get("synonyms", {}),
        }

        if family == "B":
            institution_raw.append(record)
        elif family == "A":
            service_faqs.append(record)
        else:
            general_faqs.append(record)

    # Dedup famille B par code institution (institutions_1_X / institutions_2_X
    # sont des doublons quasi identiques du meme catalogue) -- on garde la
    # version la plus riche (texte le plus long) par code.
    by_code: Dict[str, Dict] = {}
    dropped_duplicates = []
    for rec in institution_raw:
        struct = rec["reponse_struct"]
        code = clean_text(struct.get("الاختصار", "")).upper().replace(" ", "_")
        # Normalise les variantes deja couvertes par un code existant
        # (ex: "CRECHE SOCIALE" -> CRECHE, meme institution, cf. ontology.py).
        if code == "CRECHE_SOCIALE":
            code = "CRECHE"
        rec["institution_code"] = code
        if code not in by_code or len(rec["reponse_ar"]) > len(by_code[code]["reponse_ar"]):
            if code in by_code:
                dropped_duplicates.append(by_code[code]["source_id"])
            by_code[code] = rec
        else:
            dropped_duplicates.append(rec["source_id"])

    institution_enrichments = list(by_code.values())

    report = {
        "total_input": len(raw_faqs),
        "family_A_service": len(service_faqs),
        "family_B_institution_raw": len(institution_raw),
        "family_B_institution_deduped": len(institution_enrichments),
        "family_B_dropped_duplicates": dropped_duplicates,
        "family_C_general": len(general_faqs),
        "institution_codes_found": sorted(by_code.keys()),
    }
    return service_faqs, institution_enrichments, general_faqs, report
