"""Router: détecte l'intent et les entités (langue, population, région).

Corrige deux bugs v1 :
- la liste de régions était TUNISIENNE (tunis, sfax, sousse, kairouan, gafsa)
  au lieu de marocaine -> aucune extraction géo ne matchait jamais les
  vraies données (12 régions + grandes villes marocaines).
- aucun pattern arabe pour la détection d'intent, alors que l'arabe est une
  langue cible principale du chatbot -> les questions en arabe tombaient
  systématiquement sur l'intent par défaut.
"""
from typing import Dict, Any
from enum import Enum
import re


class Intent(str, Enum):
    CENTRE_SEARCH = "centre_search"
    SERVICE_SEARCH = "service_search"
    FAQ_SEARCH = "faq_search"
    PROGRAMME_2027 = "programme_2027"
    ABOUT_INSTITUTION = "about_institution"
    # Question réelle (pas une salutation) qui ne matche aucun pattern de
    # domaine connu -- 2026-08-12 : avant, ce cas tombait dans OTHER et
    # recevait la même réponse courte canned qu'un "Bonjour", ce qui n'a
    # aucun sens pour une vraie question. Reçoit un vrai tool de recherche
    # (large, sans filtre entity_type) : si des données pertinentes existent
    # malgré l'échec du pattern matching, la génération reste ancrée dessus ;
    # sinon (result_count==0), voir main.py -> réponse "connaissances
    # générales" explicitement annoncée comme telle, pas une réponse ancrée.
    OPEN_QUESTION = "open_question"
    OTHER = "other"


_AR_RANGE = re.compile(r"[؀-ۿ]")

# Salutations / politesse pures -- distinguent OTHER (réponse courte canned,
# légitime et efficace) d'OPEN_QUESTION (vraie question hors patterns connus,
# doit être traitée sérieusement, voir Intent.OPEN_QUESTION). Approche par
# soustraction (voir _is_greeting) plutôt qu'un ancrage ^...$ : couvre
# "Bonjour, merci beaucoup" (formules combinées, cf scripts/test_e2e.py #6)
# sans absorber une vraie question qui commencerait poliment.
_GREETING_WORDS_RE = re.compile(
    r"bonjour|bonsoir|salut\b|coucou|hello|hi\b|merci(\s+beaucoup)?|thanks?|"
    r"au\s+revoir|à\s+bientôt|"
    r"السلام\s+عليكم|سلام|مرحبا|أهلا(\s+وسهلا)?|صباح\s+الخير|مساء\s+الخير|"
    r"شكرا(\s+جزيلا)?|تحياتي|مع\s+السلامة|الله\s+يخليك",
    re.IGNORECASE,
)


class IntentRouter:
    """Détecte le type d'intent avec patterns heuristiques bilingues AR/FR."""

    def __init__(self):
        self.patterns = {
            Intent.CENTRE_SEARCH: [
                r"centre\s+(social|d.aide|d.accueil)",
                r"(cherche|trouver|chercher).*centre",
                r"centre\s+(EPS|CEF|CFA|CRECHE|CJPA|COAPH|CPSH|JE|CAPE|UPE)",
                r"o[uù]\s+(trouver|est|se trouve)",
                r"adresse.*centre",
                r"localisation",
                r"(أين|اين)\s+(يوجد|أجد|أقرب|توجد|تقع|يقع)",  # "اين" (sans hamza) très fréquent chez les usagers
                r"(تقع|يقع)\s+(مؤسسة|مركز)",  # verbe "être situé" manquant, trouvé en test réel (ex: "أين تقع مؤسسة JE")
                r"أقرب\s+مركز",
                r"عنوان\s+(المركز|مركز)",
                r"مركز\s+(ب|في|اجتماعي)",  # "مركز بسلا" / "مركز في..." / "مركز اجتماعي"
                # Trouvé en test réel (2026-08-14) : "ابحث عن مركز لكبار
                # السن قريب مني انا اسكن بالرباط" ne matchait AUCUN pattern
                # (ni "أقرب مركز" -- "قريب" n'est pas collé à "أقرب" ici --
                # ni "أين...") -> tombait en OPEN_QUESTION, qui n'a AUCUNE
                # expansion de graphe (voir tool_planner.py) donc aucun
                # score géographique réel malgré une région extraite -> un
                # centre à 200km de Rabat sortait en tête. Deux patterns
                # génériques manquants comblés ici.
                r"ابحث\s+عن\s+مركز",
                r"مركز.{0,20}قريب",  # "مركز ... قريب [مني]", indépendant de "أقرب"
                r"جمعية",  # association -> souvent synonyme de centre/institution
                # Darija courante (usagers réels, pas seulement arabe standard) :
                r"فين\s+(كاين|كاينة|نلقى|يوجد|هو|هي)",  # "fin kayn/nalqa..." = où est/trouver
                r"كاين\s+مركز",  # "kayn markaz" = il y a un centre
                r"y\s+a[- ]t[- ]il\s+un\s+centre",
            ],
            Intent.SERVICE_SEARCH: [
                r"service\s+(social|d.aide)",
                r"quel.*service",
                r"services?\s+pour\s+",
                r"aide\s+pour",
                r"conditions?\s+(pour|d.obtention|d.acc[eè]s)",
                r"documents?\s+(n[eé]cessaires|requis)",
                r"خدمة|خدمات",
                r"شروط",  # conditions - mot très fréquent, ne pas exiger de suite specifique
                r"وثائق|مستندات",
                r"مساعدة",
                r"إيواء|رعاية",  # hébergement / prise en charge
                # Darija courante :
                r"كيفاش\s+نستافد",  # "kifach nastafed" = comment bénéficier
                r"بغيت\s+نستافد",  # "bghit nastafed" = je veux bénéficier
                r"comment\s+b[eé]n[eé]ficier",
                r"puis-je\s+b[eé]n[eé]ficier",
                r"ai-je\s+droit",
                # Questions "qu'est-ce que [institution]" (data_faq, 2026-08-12,
                # ex: "ما هي مراكز التربية والتكوين (CEF)؟", "ما هي الفضاءات
                # متعددة الوظائف للنساء (EMF)؟") -- avant cette regle, ces
                # questions ne matchaient AUCUN intent (ما هي seul n'est pas
                # dans FAQ_SEARCH, qui exige "ما هي الخطوات" precisement) et
                # tombaient en "other" (reponse conserve, aucune recherche).
                # Pas de code latin ici (CAS/EPS/JE collisionnent avec des mots
                # FR/pronoms courants, cf entity_keywords ci-dessous) -- la
                # forme arabe plurielle suffit a couvrir les 8 fiches Institution.
                r"ما\s+(هي|هو)\s+(ال)?(مراكز|مؤسسات|وحدات|فضاءات|حضانات)",
                r"what\s+(is|are)\s+(the\s+)?(CEF|CFA|CAPE|UPE|CJPA|COAPH|CPSH|CRECHE|SAMU)",
            ],
            Intent.FAQ_SEARCH: [
                r"faq|question\s+fr[eé]quente",
                r"comment\s+(confirmer|faire|proc[eé]der)",
                r"pourquoi\s+",
                r"c.est\s+quoi",
                r"اصطياف|AOS",
                r"كيف\s+(يتم|أقوم|يمكنني)",
                r"لماذا",
                r"ما\s+هي\s+الخطوات",
                r"est-ce\s+que\s+je\s+peux",
                r"dans\s+combien\s+de\s+temps",
                r"شحال\s+من\s+الوقت",  # "chhal men lwaqt" (Darija) = combien de temps
                r"واش\s+يمكنني\s+(نأكد|نعرف|نتأكد)",  # "wach ymkenni" (Darija), gardé spécifique
                # pour ne pas absorber toute question "واش" (trop générique en Darija).
            ],
            Intent.PROGRAMME_2027: [
                r"programme\s*2027",
                r"plan.*2027",
                r"strat[eé]gie.*2027",
                r"budget.*programme",
                r"برنامج\s*2027",
                r"استراتيجية\s*2027",
                r"ميزانية",
                r"vision\s*2027",
                r"خارطة\s+الطريق",
            ],
            # Questions "méta" sur l'institution elle-même (pas sur un centre/
            # service/programme précis) : aucune donnée de ce type n'existe
            # dans la base (Centre/Service/Institution/Programme/FAQ
            # uniquement) -> plutôt que de laisser faq_search récupérer des
            # FAQ hors-sujet et produire une réponse confuse (trouvé en test
            # réel : "c'est quoi l'entraide national" retournait 5 FAQ sur la
            # réservation AOS, sans rapport), on répond par une description
            # factuelle courte, court-circuitée comme "other" (voir main.py).
            # Patterns volontairement étroits (doivent cibler l'institution
            # elle-même) pour ne pas absorber "c'est quoi le centre X".
            Intent.ABOUT_INSTITUTION: [
                r"(c.est\s+quoi|qu.est.ce\s+que)\s+(l.|la\s+)?entraide(\s+national\w*)?\s*\??$",
                r"(c.est\s+quoi|qu.est.ce\s+que)\s+ce\s+(site|assistant|chatbot|robot)",
                # (مؤسسة\s+)? optionnel : "ما هي مؤسسة التعاون الوطني" est une
                # reformulation courante trouvée en test réel qui ne matchait
                # pas la version sans "مؤسسة" -> tombait en OTHER (2026-08-12).
                r"(ما\s+هو|ما\s+هي|شنو\s+هو|واش\s+هو|وشنو\s+هو)\s+(مؤسسة\s+)?(التعاون\s+الوطني|التعاون)\b",
                r"من\s+(أنت|انتم|انت)\s*\؟?$",
            ],
        }

        # Régions officielles du Maroc (découpage 2015) + grandes villes/centres
        self.entity_keywords = {
            "population_type": {
                "enfants": ["enfant", "enfants", "أطفال", "الأطفال", "طفل"],
                "femmes": ["femme", "femmes", "نساء", "النساء", "امرأة"],
                "personnes_agees": ["personnes âgées", "personne âgée", "senior", "مسن", "المسنين", "كبار السن"],
                "personnes_handicapees": ["handicap", "handicapé", "psh", "إعاقة", "معاق", "ذوي الإعاقة", "ذوي الاحتياجات"],
                "jeunes": ["jeune", "jeunes", "شباب", "الشباب"],
            },
            "regions": [
                "tanger-tétouan-al hoceïma", "tanger", "tétouan", "al hoceïma",
                "l'oriental", "oriental", "oujda", "nador",
                "fès-meknès", "fès", "fes", "meknès", "meknes", "taza",
                "rabat-salé-kénitra", "rabat", "salé", "sale", "kénitra", "kenitra", "khémisset", "khemisset",
                "béni mellal-khénifra", "béni mellal", "beni mellal", "khénifra", "khouribga",
                "casablanca-settat", "casablanca", "settat", "berrechid", "el jadida", "mohammedia",
                "marrakech-safi", "marrakech", "safi", "essaouira",
                "drâa-tafilalet", "drâa", "tafilalet", "errachidia", "ouarzazate", "midelt",
                "souss-massa", "agadir", "taroudant", "tiznit",
                "guelmim-oued noun", "guelmim", "tan-tan",
                "laâyoune-sakia el hamra", "laâyoune", "laayoune",
                "dakhla-oued ed-dahab", "dakhla",
                "المغرب", "الرباط", "الدار البيضاء", "فاس", "مراكش", "طنجة", "أكادير", "وجدة", "سلا",
            ],
            # mot-clé -> code institution réel (celui stocké dans payload["institutions"]
            # côté Qdrant/Neo4j). Un simple .upper() sur un mot arabe est un no-op et
            # produisait un filtre sur une valeur ("حضانة") qui n'existe dans aucun
            # payload -> 0 résultat silencieux (bug trouvé en test e2e, voir #1/#7).
            "institutions": {
                "cef": "CEF", "cfa": "CFA",
                "creche": "CRECHE", "crèche": "CRECHE", "حضانة": "CRECHE",
                "je": "JE", "روض الأطفال": "JE", "jardin d'enfants": "JE",
                "cape": "CAPE", "upe": "UPE", "cjpa": "CJPA",
                "coaph": "COAPH", "cpsh": "CPSH", "eps": "EPS",
                # Découverts en analysant ~/Downloads/data_faq (2026-08-12).
                # "CAS" est aussi un mot français courant ("dans ce cas...")
                # -> même traitement que "je" (voir plus bas) : match
                # casse-sensible uniquement, pour éviter un filtre
                # institution déclenché à tort sur du texte français normal.
                "CAS": "CAS", "مراكز المساعدة الاجتماعية": "CAS",
                "emf": "EMF", "الفضاءات متعددة الوظائف": "EMF",
                "samu social": "SAMU_SOCIAL", "samu_social": "SAMU_SOCIAL",
                "الإسعاف الاجتماعي المتنقل": "SAMU_SOCIAL",
            },
        }

    def route(self, query: str) -> Dict[str, Any]:
        query_norm = query.strip()
        query_lower = query_norm.lower()

        intent = self._detect_intent(query_lower)
        entities = self._extract_entities(query_lower)
        language = self._detect_language(query_norm)

        return {
            "intent": intent,
            "language": language,
            "original_query": query,
            "normalized_query": query_lower,
            "entities": entities,
            "confidence": self._calculate_confidence(intent, entities),
        }

    def _detect_language(self, query: str) -> str:
        ar_chars = len(_AR_RANGE.findall(query))
        total = max(len(query.replace(" ", "")), 1)
        if ar_chars / total > 0.3:
            return "ar"
        if ar_chars > 0:
            return "mixed"
        return "fr"

    # Ordre de priorité explicite en cas d'égalité de score (pas l'ordre du
    # dict, trop fragile). ABOUT_INSTITUTION d'abord : ses patterns sont très
    # étroits (ciblent l'institution elle-même) mais partagent le mot-clé
    # "c'est quoi" avec FAQ_SEARCH (large) -> sans cette priorité, l'égalité
    # de score se résout arbitrairement et "c'est quoi l'entraide national"
    # peut retomber en faq_search (bug réel trouvé en test, voir patterns
    # ci-dessus). FAQ_SEARCH et PROGRAMME_2027 ont ensuite des mots-clés très
    # specifiques ("اصطياف/AOS", "2027") -> priorite sur SERVICE_SEARCH dont
    # "شروط" est volontairement large et matche presque toute question de
    # conditions. Bug reel trouve en evaluation : "شروط الاستفادة من
    # الاصطياف" partait en service_search (qui exclut les FAQ du retrieval)
    # au lieu de faq_search -> reponse hors-sujet (programme d'alphabetisation
    # au lieu du vrai FAQ AOS).
    _INTENT_PRIORITY = [
        Intent.ABOUT_INSTITUTION, Intent.FAQ_SEARCH, Intent.PROGRAMME_2027,
        Intent.CENTRE_SEARCH, Intent.SERVICE_SEARCH,
    ]

    def _is_greeting(self, query: str) -> bool:
        """Vrai si, une fois les formules de politesse connues retirées, il
        ne reste plus que ponctuation/espaces -- "Bonjour" et "Bonjour,
        merci beaucoup" sont des salutations pures ; "Bonjour, quelles sont
        les conditions..." ne l'est pas (reste substantiel après retrait)."""
        remainder = _GREETING_WORDS_RE.sub(" ", query)
        remainder = re.sub(r"[!.,؟?\s]+", "", remainder)
        return len(remainder) == 0

    def _detect_intent(self, query: str) -> str:
        scores = {}
        for intent, patterns in self.patterns.items():
            score = sum(1 for p in patterns if re.search(p, query, re.IGNORECASE))
            scores[intent] = score

        max_score = max(scores.values())
        if max_score == 0:
            return Intent.OTHER.value if self._is_greeting(query) else Intent.OPEN_QUESTION.value
        for intent in self._INTENT_PRIORITY:
            if scores.get(intent) == max_score:
                return intent.value
        return Intent.OTHER.value

    def _extract_entities(self, query: str) -> Dict[str, list]:
        entities = {"population_types": [], "regions": [], "institutions": []}

        for pop_code, keywords in self.entity_keywords["population_type"].items():
            if any(kw in query for kw in keywords):
                entities["population_types"].append(pop_code)

        for region in self.entity_keywords["regions"]:
            if region in query:
                entities["regions"].append(region)

        for keyword, code in self.entity_keywords["institutions"].items():
            # "je" (JE = Jardin d'Enfants) collide avec le pronom francais,
            # "CAS" avec le mot francais courant ("dans ce cas...") -> match
            # casse-sensible uniquement pour ces mots ambigus (trouve en test :
            # "Je cherche un centre EPS" detectait JE a tort).
            flags = 0 if keyword in ("je", "CAS") else re.IGNORECASE
            if re.search(rf"\b{re.escape(keyword)}\b", query, flags):
                if code not in entities["institutions"]:
                    entities["institutions"].append(code)

        return entities

    def _calculate_confidence(self, intent: str, entities: Dict) -> float:
        confidence = 0.6
        if any(entities.values()):
            confidence += 0.2
        entity_count = sum(len(v) for v in entities.values())
        if entity_count >= 2:
            confidence += 0.1
        return min(confidence, 1.0)
