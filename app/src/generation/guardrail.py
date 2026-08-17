"""Guardrail: détecte hallucinations et incohérences de langue avant renvoi.

La v1 lisait déjà `result.get("name")` mais context_builder ne le
remplissait jamais (payload pauvre) -> `context_keywords` restait
quasi vide et la vérification ne servait à rien en pratique. Corrigé de
facto par la réparation de context_builder.py (payload enrichi).

v2 (évaluation profonde) : la v1 ne détectait QUE "contexte totalement vide"
+ quelques patterns numériques très étroits ("il existe X", "le nombre de X
est"). Elle ratait le cas réel trouvé en test faithfulness : une réponse
fluide citant un programme/des chiffres d'un contexte non pertinent (mauvais
intent) passait `guardrail_valid=True` car le contexte n'était pas vide et
aucun des patterns étroits ne matchait la phrase. On ajoute ici une vraie
vérification de citation : codes d'institution cités vs `institutions` du
contexte, nombres/pourcentages/durées cités vs texte brut du contexte, et un
score de recouvrement lexical global (réponse vs texte concaténé du
contexte) pour repérer une réponse qui "dérive" hors-sujet même sans
assertion chiffrée explicite.
"""
from typing import Dict, Any, Tuple, List
import re


_INSTITUTION_CODES = {"CEF", "CFA", "CRECHE", "JE", "CAPE", "UPE", "CJPA", "COAPH", "CPSH", "EPS"}
_INSTITUTION_CODE_RE = re.compile(r"\b(" + "|".join(_INSTITUTION_CODES) + r")\b")
# nombre + unité fréquente dans ce domaine (délais, taux de prise en charge,
# montants) -> ce sont exactement les chiffres qui, cités hors-contexte,
# constituent l'hallucination la plus trompeuse (précise mais fausse).
_NUMERIC_CLAIM_RE = re.compile(
    r"\b\d{1,4}(?:[.,]\d+)?\s*(?:%|٪|درهم|دولار|MAD|dh|dhs?|heures?|ساعة|ساعات|jours?|أيام|يوما?|mois|أشهر|شهرا?|ans?|سنوات|سنة)\b",
    re.IGNORECASE,
)
_STOPWORDS = {
    "the", "and", "for", "with", "que", "les", "des", "une", "dans", "pour", "sur", "est", "sont",
    "من", "على", "إلى", "في", "أن", "التي", "الذي", "هذا", "هذه", "أو", "و", "كما", "يتم", "عن", "مع",
}


class ResponseGuardrail:
    def __init__(self):
        self.context_keywords: set = set()
        self.context_text: str = ""
        self.context_tokens: set = set()
        self.allowed_institutions: set = set()
        self.allowed_entities: List[Dict] = []
        self.expected_language: str = ""

    def set_context(self, context_json: Dict[str, Any], expected_language: str = "") -> None:
        self.expected_language = expected_language
        self.context_keywords = set()
        self.allowed_institutions = set()
        self.allowed_entities = context_json.get("results", [])
        text_parts: List[str] = []
        for result in self.allowed_entities:
            for value in (result.get("name"), result.get("type"), result.get("population_cible")):
                if value:
                    self.context_keywords.add(str(value).lower())
                    text_parts.append(str(value))
            for inst in result.get("institutions", []) or []:
                self.context_keywords.add(str(inst).lower())
                self.allowed_institutions.add(str(inst).upper())
            for field in ("conditions", "documents"):
                for v in result.get(field, []) or []:
                    text_parts.append(str(v))
            if result.get("text"):
                text_parts.append(str(result["text"]))
        self.context_text = " ".join(text_parts)
        self.context_tokens = self._tokenize(self.context_text)

    def validate_response(self, response: str) -> Tuple[bool, str, Dict[str, Any]]:
        issues = {"hallucinations": [], "language_errors": [], "format_errors": []}
        is_valid = True

        if not self.allowed_entities:
            # Pas de contexte pertinent trouvé : la réponse doit le dire, pas inventer.
            if not self._is_no_info_response(response):
                issues["hallucinations"].append("Contexte vide mais réponse affirmative")
                is_valid = False

        hallucinations = self._detect_hallucinations(response)
        if hallucinations:
            issues["hallucinations"].extend(hallucinations)
            is_valid = False

        # Vérification de citation réelle : ne se déclenche que si un contexte
        # existe (sinon c'est déjà couvert par le cas "contexte vide" ci-dessus).
        if self.allowed_entities:
            citation_issues = self._detect_uncited_claims(response)
            if citation_issues:
                issues["hallucinations"].extend(citation_issues)
                is_valid = False

            grounding_issue = self._check_topical_grounding(response)
            if grounding_issue:
                issues["hallucinations"].append(grounding_issue)
                is_valid = False

        language_issues = self._check_language(response)
        if language_issues:
            issues["language_errors"] = language_issues
            is_valid = False

        issues["format_errors"] = self._check_format(response)

        cleaned = self._clean_response(response)
        return is_valid, cleaned, issues

    def _is_no_info_response(self, response: str) -> bool:
        markers = ["je ne dispose pas", "لا أتوفر على", "ليس لدي معلومات", "pas cette information"]
        return any(m in response.lower() for m in markers)

    def _detect_hallucinations(self, response: str) -> list:
        hallucinations = []
        assertion_patterns = [
            r"il existe\s+(\d+)", r"le nombre de\s+(.+?)\s+est",
            r"nous avons\s+(.+?)\s+centres", r"il y a\s+(\d+)",
            r"يوجد\s+(\d+)", r"عدد\s+(.+?)\s+هو",
        ]
        for pattern in assertion_patterns:
            for match in re.findall(pattern, response, re.IGNORECASE):
                if not self._is_in_context(str(match)):
                    hallucinations.append(f"Assertion non vérifiée: {match}")
        return hallucinations

    def _check_language(self, response: str) -> list:
        issues = []
        if not response.strip():
            return ["Réponse vide"]

        # 2026-08-14 : fuite de caractères chinois observée à deux reprises
        # en test réel (Qwen2.5 -- artefact connu de ces modèles sino-
        # entraînés, surtout en fin de génération ou sur du texte structuré
        # avec des titres "###"). Le check ar_ratio/fr_ratio ci-dessous ne
        # les détecte pas (ni arabe ni latin-ascii, donc ignorés des deux
        # ratios) -- ex vu en test : "...请输入您希望翻译成中文的内容" ajouté
        # après une réponse arabe par ailleurs correcte. Détecté à part et
        # invalidé systématiquement, quelle que soit la langue attendue.
        cjk_chars = len([c for c in response if "一" <= c <= "鿿"])
        if cjk_chars > 0:
            issues.append(f"Caractères chinois détectés dans la réponse ({cjk_chars} caractères) -- artefact du modèle, jamais légitime ici")

        ar_chars = len([c for c in response if "؀" <= c <= "ۿ"])
        fr_chars = len([c for c in response if c.isalpha() and c.isascii()])
        total = len(response)
        ar_ratio, fr_ratio = ar_chars / total, fr_chars / total
        if ar_ratio < 0.05 and fr_ratio < 0.05:
            issues.append("Pas de contenu linguistique valide")
            return issues

        # Cohérence avec la langue de la question (2026-08-13, demande
        # explicite : "obligatoire de répondre dans la même langue que la
        # requête"). Comparatif ratio-vs-ratio, pas un seuil absolu : une
        # réponse arabe légitime contient souvent des codes/acronymes latins
        # (CEF, CFA...) sans que ça signifie qu'elle a été rédigée en français.
        if self.expected_language == "ar" and fr_ratio > ar_ratio:
            issues.append(f"Langue attendue arabe mais réponse majoritairement latine (ar={ar_ratio:.2f} fr={fr_ratio:.2f})")
        elif self.expected_language == "fr" and ar_ratio > fr_ratio:
            issues.append(f"Langue attendue française mais réponse majoritairement arabe (ar={ar_ratio:.2f} fr={fr_ratio:.2f})")
        return issues

    def _check_format(self, response: str) -> list:
        issues = []
        if len(response) < 10:
            issues.append("Réponse trop courte")
        elif len(response) > 2000:
            issues.append("Réponse trop longue (tronquée)")
        return issues

    def _clean_response(self, response: str) -> str:
        if len(response) > 1500:
            return response[:1500] + "..."
        return response

    def _is_in_context(self, fact: str) -> bool:
        fact_lower = fact.lower()
        return any(kw in fact_lower or fact_lower in kw for kw in self.context_keywords)

    def _tokenize(self, text: str) -> set:
        # Mots (latin ou arabe) de 3 caractères ou plus, hors stopwords -
        # assez large pour capter le vocabulaire métier (noms de programmes,
        # codes, termes spécifiques) sans se noyer dans les mots outils.
        words = re.findall(r"[a-zA-ZàâäéèêëïîôöùûüçÀ-ÿ؀-ۿ]{3,}", text.lower())
        return {w for w in words if w not in _STOPWORDS}

    def _detect_uncited_claims(self, response: str) -> List[str]:
        """Vérifie que les codes d'institution et les chiffres/durées cités
        dans la réponse apparaissent réellement dans le contexte fourni.

        Cible précisément le cas trouvé en évaluation faithfulness : le LLM
        cite un chiffre précis (délai, taux de prise en charge) qui semble
        crédible mais provient d'une autre entité que celle que la réponse
        prétend décrire, ou d'aucune entité du contexte du tout."""
        issues = []

        cited_codes = set(_INSTITUTION_CODE_RE.findall(response))
        unverified_codes = cited_codes - self.allowed_institutions
        if unverified_codes:
            issues.append(
                f"Institution(s) citée(s) absente(s) du contexte: {', '.join(sorted(unverified_codes))}"
            )

        for match in _NUMERIC_CLAIM_RE.finditer(response):
            claim = match.group(0).strip()
            digits = re.sub(r"[^\d.,]", "", claim)
            # cherche le nombre exact dans le texte du contexte (peu importe
            # l'unité/la mise en forme autour) plutôt que le pattern complet,
            # qui varie trop entre langues (ex: "48 ساعة" vs "48h").
            if digits and digits not in re.sub(r"[^\d.,]", " ", self.context_text):
                issues.append(f"Chiffre cité non retrouvé dans le contexte: {claim}")

        return issues

    def _check_topical_grounding(self, response: str) -> str:
        """Signal complémentaire (pas une preuve à lui seul) : une réponse
        substantielle qui ne partage presque aucun mot significatif avec le
        contexte retrouvé est probablement une dérive hors-sujet plutôt
        qu'une vraie synthèse du contexte - même sans chiffre inventé."""
        if len(response.strip()) < 80 or not self.context_tokens:
            return ""
        response_tokens = self._tokenize(response)
        if not response_tokens:
            return ""
        overlap = response_tokens & self.context_tokens
        ratio = len(overlap) / len(response_tokens)
        if ratio < 0.08:
            return f"Recouvrement lexical très faible avec le contexte ({ratio:.0%})"
        return ""
