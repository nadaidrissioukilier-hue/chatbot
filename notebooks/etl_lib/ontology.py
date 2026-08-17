"""Ontologie métier ENTRADE.MA — module central figé (Phase 00).

Utilisé par tous les notebooks 01->06. Toute règle métier (institutions,
populations, régions valides, IDs stables) est définie ICI UNE SEULE FOIS,
pour éviter la dérive constatée dans les versions précédentes (chaque
notebook réinventait sa propre logique de matching, avec des structures de
données différentes de celles réellement présentes dans rag data/).
"""
import hashlib
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

# ===================== INSTITUTIONS =====================
INSTITUTION_MAP: Dict[str, Dict] = {
    "CEF": {"ar": "مراكز التربية والتكوين", "fr": "Centre d'Éducation et de Formation",
            "polyvalence": 2, "population_cibles": ["femmes", "jeunes"], "axe_principal": "Formation professionnelle"},
    "CFA": {"ar": "مراكز التكوين بالتدرج المهني", "fr": "Centre de Formation par Apprentissage",
            "polyvalence": 1, "population_cibles": ["jeunes"], "axe_principal": "Formation professionnelle"},
    "CAPE": {"ar": "مراكز المواكبة لحماية الطفولة", "fr": "Centre d'Accompagnement pour la Protection de l'Enfance",
             "polyvalence": 1, "population_cibles": ["enfants"], "axe_principal": "Protection Enfance"},
    "UPE": {"ar": "وحدات حماية الطفولة", "fr": "Unité de Protection de l'Enfance",
            "polyvalence": 1, "population_cibles": ["enfants"], "axe_principal": "Protection Enfance"},
    "EPS": {"ar": "مؤسسات الرعاية الاجتماعية", "fr": "Établissement de Protection Sociale",
            "polyvalence": 5, "population_cibles": ["enfants", "femmes", "personnes_agees", "personnes_handicapees"],
            "axe_principal": "Assistance Sociale"},
    "CJPA": {"ar": "المراكز الاجتماعية للخدمات النهارية للأشخاص المسنين", "fr": "Centre de Jour pour Personnes Âgées",
             "polyvalence": 2, "population_cibles": ["personnes_agees"], "axe_principal": "Petite Enfance"},
    "COAPH": {"ar": "مراكز توجيه ومساعدة الأشخاص في وضعية إعاقة", "fr": "Centre d'Orientation et d'Aide aux Personnes Handicapées",
              "polyvalence": 2, "population_cibles": ["personnes_handicapees"], "axe_principal": "Insertion Sociale"},
    "CPSH": {"ar": "مراكز تأهيل وإدماج الأشخاص في وضعية إعاقة", "fr": "Centre de Promotion Sociale des Handicapés",
             "polyvalence": 2, "population_cibles": ["personnes_handicapees"], "axe_principal": "Insertion Sociale"},
    "CRECHE": {"ar": "حضانة", "fr": "Crèche",
               "polyvalence": 1, "population_cibles": ["enfants"], "axe_principal": "Petite Enfance"},
    "JE": {"ar": "روض الأطفال", "fr": "Jardin d'Enfants",
           "polyvalence": 1, "population_cibles": ["enfants"], "axe_principal": "Petite Enfance"},
    "CAREPS": {"ar": "مراكز الرعاية والتأهيل", "fr": "Centre de Rééducation et Réadaptation",
               "polyvalence": 3, "population_cibles": ["personnes_handicapees"], "axe_principal": "Insertion Sociale"},
    # Découverts en analysant ~/Downloads/data_faq (institutions_1/2.json,
    # familles institutionnelles absentes des sources d'origine du guide).
    "CAS": {"ar": "مراكز المساعدة الاجتماعية", "fr": "Centre d'Assistance Sociale",
            "polyvalence": 5, "population_cibles": ["enfants", "femmes", "personnes_agees", "personnes_handicapees", "famille"],
            "axe_principal": "Assistance Sociale"},
    "EMF": {"ar": "الفضاءات متعددة الوظائف للنساء", "fr": "Espace Multifonctionnel Femmes",
            "polyvalence": 1, "population_cibles": ["femmes"], "axe_principal": "Insertion Sociale"},
    "SAMU_SOCIAL": {"ar": "مؤسسات الإسعاف الاجتماعي المتنقل", "fr": "SAMU Social",
                     "polyvalence": 1, "population_cibles": ["famille"], "axe_principal": "Assistance Sociale"},
}
EPS_CODE = "EPS"

# Motifs de reconnaissance par code (texte libre -> code institution).
# Basé sur les libellés réellement observés dans rag data/ (ex: "mراكز
# المواكبة لحماية الطفولة (CAPE)", "activite": "CEF"...).
_INSTITUTION_PATTERNS: Dict[str, List[str]] = {
    "CEF": [r"\bcef\b", r"éducation et de formation", r"مراكز التربية والتكوين"],
    "CFA": [r"\bcfa\b", r"formation par apprentissage", r"التكوين بالتدرج المهني"],
    "CAPE": [r"\bcape\b", r"مواكبة لحماية الطفولة"],
    "UPE": [r"\bupe\b", r"وحدات حماية الطفولة"],
    "CJPA": [r"\bcjpa\b", r"جمعية.*مسنين", r"الخدمات النهارية للأشخاص المسنين"],
    "COAPH": [r"\bcoaph\b", r"توجيه ومساعدة.*إعاقة"],
    "CPSH": [r"\bcpsh\b", r"تأهيل وإدماج.*إعاقة"],
    "CRECHE": [r"\bcr[eè]che\b", r"^حضانة", r"حضانة اجتماعية"],
    "JE": [r"\bje\b", r"jardin d.enfants?", r"روض الأطفال"],
    "CAREPS": [r"\bcareps\b", r"رعاية وتأهيل"],
    "EPS": [r"\beps\b", r"الرعاية الاجتماعية", r"établissement.*protection sociale"],
    # NB: pas de \bcas\b nu ici -- "cas" est un mot francais courant ("dans ce
    # cas...") et matcherait de faux positifs sur tout texte FR. On exige la
    # forme parenthesee (comme les autres codes: "... (CAPE)") ou l'arabe.
    "CAS": [r"\(cas\)", r"مراكز المساعدة الاجتماعية"],
    "EMF": [r"\bemf\b", r"الفضاءات متعددة الوظائف للنساء", r"espace.*multifonctionnel"],
    "SAMU_SOCIAL": [r"samu\s*social", r"الإسعاف الاجتماعي المتنقل"],
}
_COMPILED_PATTERNS = {code: [re.compile(p, re.IGNORECASE) for p in pats] for code, pats in _INSTITUTION_PATTERNS.items()}

# ===================== POPULATIONS CIBLES =====================
POPULATION_CIBLES: Dict[str, Dict] = {
    "enfants": {"ar": "الأطفال", "fr": "Enfants", "priorite": 1,
                "keywords": ["enfant", "طفل", "أطفال", "enfants_0_3", "enfants_15_18"]},
    "femmes": {"ar": "النساء", "fr": "Femmes", "priorite": 2,
               "keywords": ["femme", "نساء", "امرأة", "المرأة"]},
    "personnes_agees": {"ar": "المسنين", "fr": "Personnes Âgées", "priorite": 3,
                         "keywords": ["personne", "âgée", "senior", "مسن"]},
    "personnes_handicapees": {"ar": "الأشخاص ذوو الإعاقة", "fr": "Personnes Handicapées", "priorite": 4,
                               "keywords": ["handicap", "إعاقة", "معاق"]},
    "jeunes": {"ar": "الشباب", "fr": "Jeunes", "priorite": 5, "keywords": ["jeune", "شباب"]},
    "famille": {"ar": "الأسرة", "fr": "Famille", "priorite": 6, "keywords": ["famille", "أسرة"]},
}

# 12 régions officielles du Maroc (découpage 2015) — sert à valider la
# géographie de centres.jsonl, dont le guide signale un bruit élevé.
MOROCCAN_REGIONS = {
    "Tanger-Tétouan-Al Hoceïma", "L'Oriental", "Fès-Meknès", "Rabat-Salé-Kénitra",
    "Béni Mellal-Khénifra", "Casablanca-Settat", "Marrakech-Safi", "Drâa-Tafilalet",
    "Souss-Massa", "Guelmim-Oued Noun", "Laâyoune-Sakia El Hamra", "Dakhla-Oued Ed-Dahab",
}

# La saisie réelle de centres.jsonl varie beaucoup dans l'orthographe des
# régions ("Beni" sans accent, "Oriental" sans "L'", "Hoceima" sans tréma,
# "Saguia" au lieu de "Sakia"...). Un matching exact rejette ~46% de centres
# par ailleurs légitimes. On normalise via un matching flou plutôt qu'une
# whitelist figée — voir normalize_region().
def normalize_region(raw_region: str, threshold: int = 78) -> Optional[str]:
    """Fait correspondre une valeur région brute (orthographe libre) à l'un
    des 12 noms canoniques, par similarité floue. Retourne None si aucune
    région ne correspond suffisamment (probable bruit/champ décalé, ex:
    'Province El Kelaa des Sraghna\"' trouvé dans centres.jsonl)."""
    if not raw_region:
        return None
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return raw_region if raw_region in MOROCCAN_REGIONS else None

    raw_clean = clean_text(raw_region).rstrip('"').strip()
    best_region, best_score = None, 0
    for region in MOROCCAN_REGIONS:
        score = fuzz.ratio(raw_clean.lower(), region.lower())
        if score > best_score:
            best_region, best_score = region, score
    return best_region if best_score >= threshold else None


def clean_text(text: Optional[str]) -> str:
    """Nettoie un texte source (None-safe, espaces multiples, sauts de ligne)."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_arabic(text: str) -> str:
    """Normalisation arabe pour comparaison/matching (pas pour affichage) :
    diacritiques, hamzas, ta marbouta, alif maqsura, casse latine."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ً-ٰٟ]", "", text)  # diacritiques
    text = text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي")
    text = text.replace("ة", "ه")
    text = text.replace("ـ", "")  # tatweel
    return clean_text(text).lower()


def stable_id(prefix: str, *parts: str) -> str:
    """ID déterministe (même entrée -> même ID, sur toutes les phases et
    entre Neo4j et Qdrant)."""
    normalized = "_".join(normalize_arabic(clean_text(p)) for p in parts if p)
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def extract_institutions(text: str) -> Tuple[List[str], bool]:
    """Extrait les codes institution présents dans un texte libre.
    Retourne (codes, eps_fallback) — eps_fallback=True si aucune institution
    n'a été détectée et qu'EPS a été utilisé par défaut (dernier recours)."""
    if not text:
        return [EPS_CODE], True
    found = []
    for code, patterns in _COMPILED_PATTERNS.items():
        if any(p.search(text) for p in patterns):
            found.append(code)
    if not found:
        return [EPS_CODE], True
    # dédupliquer en conservant l'ordre
    seen = set()
    ordered = [c for c in found if not (c in seen or seen.add(c))]
    return ordered, False


def match_population(text: str) -> List[str]:
    """Détecte les populations cibles mentionnées dans un texte libre."""
    if not text:
        return []
    text_norm = normalize_arabic(text)
    matched = []
    for code, data in POPULATION_CIBLES.items():
        if any(normalize_arabic(kw) in text_norm for kw in data["keywords"]):
            matched.append(code)
    return matched or ["famille"]
