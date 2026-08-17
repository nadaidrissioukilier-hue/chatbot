"""API FastAPI — ENTRADE.MA GraphRAG (VM2).

Corrige les bugs v1 :
- `self._fallback_response(...)` appelé depuis une fonction de module (pas
  une méthode) -> NameError garanti sur le chemin de secours. Corrigé en
  fonction de module normale, appelée sans `self`.
- /chat/stream envoyait la question brute au LLM sans retrieval -> utilise
  maintenant le même pipeline que /chat (src/retrieval/pipeline.py), seule la
  génération finale est en streaming.
- /health renvoyait des statuts codés en dur -> vraies vérifications
  (ping Neo4j, get_collections Qdrant, PING Redis, /health llama.cpp).
- /ingest/* étaient des stubs vides -> déclenchent réellement les scripts
  d'ingestion en tâche de fond.
- /metrics renvoyait un stub -> vraies métriques Prometheus.
- Aucune route n'était authentifiée -> API Key (widget) / JWT (admin).
"""
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from src.config import (
    API_HOST, API_PORT, ENABLE_METRICS, ALLOWED_ORIGINS,
    GROUNDED_MAX_TOKENS, GENERAL_KNOWLEDGE_MAX_TOKENS, CONTEXT_TOP_N_PROMPT,
)
from src.retrieval import pipeline
from src.generation.guardrail import ResponseGuardrail
from src.inference.llamacpp_client import LlamaCppClient
from src.tools.redis_cache import RedisCache
from src.tools.graph_search import GraphSearch
from src.tools.calculator import try_calculate
from src.tools.text_normalize import normalize_query
from src.tools.session_memory import SessionMemory
from src.auth import require_widget_key, require_admin, create_access_token, verify_admin_credentials

SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts"
SYSTEM_PROMPT = (
    "Tu es un assistant officiel de l'Entraide Nationale (Maroc).\n"
    "Tu réponds uniquement à partir du contexte fourni.\n"
    "- Langue = langue de la question (arabe ou français)\n"
    "- Ne jamais inventer conditions, documents, centres ou programmes\n"
    "- Si information absente -> le dire clairement et orienter vers le centre le plus proche\n"
    "- Va droit au but : commence directement par la réponse utile, sans salutation ni préambule\n"
    # 2026-08-13 ("donner le max de text data") : avant "concises... 5 à 8
    # lignes maximum" -- inversé. Le contexte transmis est maintenant plus
    # riche (voir CONTEXT_TOP_N_PROMPT/CONTEXT_TEXT_TRUNCATE dans config.py),
    # donc la consigne de brièveté allait activement à l'encontre de la
    # demande : le LLM tronquait volontairement une réponse déjà préparée.
    "- Sois complet et détaillé : traite CHAQUE élément pertinent du contexte "
    "(chaque population/centre/service concerné), pas seulement le premier\n"
    "- Cite systématiquement centres, conditions, documents et institutions quand disponibles, "
    "sous forme de liste structurée avec des tirets, une section par catégorie si plusieurs s'appliquent\n"
    "- Texte brut uniquement : jamais de markdown (pas de **gras**, pas de #titres, pas de ```code```)\n"
    "- La longueur suit le besoin réel de la question : ne coupe pas une information pertinente pour \"faire court\""
)

# 2026-08-12 : mode "connaissances générales" -- pour Intent.OPEN_QUESTION
# confirmé hors domaine (recherche large sans résultat, voir tool_planner.py
# et main.py::chat). Contrairement à SYSTEM_PROMPT (qui interdit toute
# réponse hors contexte fourni, correct pour les données Entraide), ce
# prompt autorise explicitement les connaissances générales du modèle --
# la distinction avec la base de données est garantie par _GENERAL_KNOWLEDGE_DISCLOSURE
# ci-dessous (préfixe fixe, pas laissé à la discrétion du LLM).
GENERAL_KNOWLEDGE_SYSTEM_PROMPT = (
    "Tu es un assistant conversationnel généraliste, utile et honnête.\n"
    "La question posée ne concerne pas les services de l'Entraide Nationale "
    "et aucune donnée pertinente n'existe dans sa base : réponds avec tes "
    "connaissances générales.\n"
    "- Langue = langue de la question (arabe ou français)\n"
    "- Texte brut uniquement : jamais de markdown (pas de **gras**, pas de #titres)\n"
    "- Réponse concise, 3 à 6 lignes maximum\n"
    "- Si tu n'es pas sûr d'un fait précis, dis-le plutôt que d'inventer"
)

_GENERAL_KNOWLEDGE_DISCLOSURE = {
    "ar": "(معلومة عامة، ليست من قاعدة بيانات التعاون الوطني) ",
    "fr": "(Connaissance générale, hors base de données de l'Entraide Nationale) ",
}

# Seuil de pertinence pour Intent.OPEN_QUESTION : `result_count` ne peut PAS
# servir ici -- une recherche vectorielle sans filtre entity_type renvoie
# toujours les "plus proches voisins", même sans rapport réel (vérifié en
# test réel : "ما هي عاصمة اليابان؟" (capitale du Japon) donnait 10 résultats
# avec final_score jusqu'à 0.54, present comme des données pertinentes).
# `reranker_score` (cross-encoder BGE-v2-m3, comparaison sémantique réelle
# query<->passage) discrimine correctement : mesuré à 0.94-0.99 sur de vraies
# correspondances (ex. question CEF), 0.0 sur la question Japon -- marge large.
OPEN_QUESTION_RELEVANCE_THRESHOLD = 0.4


def _best_reranker_score(context_obj: Dict) -> float:
    results = context_obj["json_context"]["results"]
    if not results:
        return 0.0
    return max(r["scores"].get("reranker_score", 0.0) for r in results)


# Intents dont le PATTERN d'activation est déjà un signal de pertinence
# métier suffisant (mots-clés propres au domaine : "شروط", "اصطياف/AOS",
# "programme 2027"...) -- pour ceux-là, le gate sémantique strict ci-dessous
# n'est PAS appliqué (voir _is_relevant). open_question/about_institution
# restent seuls soumis au gate strict : ce sont les deux seuls cas où AUCUNE
# preuve préalable de pertinence n'existe (open_question = par définition
# aucun pattern de domaine n'a matché ; about_institution partage son
# mot-clé large "c'est quoi" avec des questions générales, cf. patterns).
_STRICT_GATE_INTENTS = {"open_question", "about_institution"}


def _is_relevant(retrieval: Dict) -> bool:
    """RELEVANCE GATE. Deux régimes distincts (2026-08-13, ajusté après deux
    faux-négatifs réels en test) :

    - Intents de domaine étroitement pattern-matchés (centre_search,
      service_search, faq_search, programme_2027) : toujours considérés
      pertinents (le pattern d'activation EST le signal). Le seul
      reranker_score s'est révélé trop peu fiable ici -- vérifié en test
      réel : "أين أجد أقرب حضانة في سلا؟" (Centre, adresse admin
      FR/latin) ET "...الاستفادة من الاصطياف؟" (FAQ AOS légitime) obtiennent
      TOUTES DEUX reranker_score=0.0, exactement comme une vraie question
      hors-domaine (capitale du Japon) -- aucun seuil ne peut les distinguer
      sur ce seul signal. Le guardrail (_check_topical_grounding,
      _detect_uncited_claims) reste le filet de sécurité si la génération
      dérive quand même hors-sujet malgré un contexte récupéré pertinent.
    - open_question / about_institution : gate strict, reranker_score OU
      entités extraites (population/institution/région -- vocabulaire propre
      au domaine, fiable même quand le reranker échoue, cf. cas Creche
      Valerius ci-dessus)."""
    if retrieval["intent"] not in _STRICT_GATE_INTENTS:
        return retrieval["result_count"] > 0
    if _best_reranker_score(retrieval["context"]) >= OPEN_QUESTION_RELEVANCE_THRESHOLD:
        return True
    entities = retrieval.get("entities", {})
    return bool(entities.get("population_types") or entities.get("institutions") or entities.get("regions"))


def _language_matches(response: str, expected_language: str) -> bool:
    """Même règle comparative que ResponseGuardrail._check_language, utilisée
    ici pour le chemin "connaissances générales" qui ne passe pas par le
    guardrail complet (pas de contexte à vérifier, juste la langue)."""
    if not response.strip():
        return True
    # Fuite de caractères chinois (Qwen2.5, voir guardrail.py) -- jamais
    # légitime ici, quelle que soit expected_language.
    if any("一" <= c <= "鿿" for c in response):
        return False
    if expected_language not in ("ar", "fr"):
        return True
    ar_ratio = len([c for c in response if "؀" <= c <= "ۿ"]) / len(response)
    fr_ratio = len([c for c in response if c.isalpha() and c.isascii()]) / len(response)
    return ar_ratio >= fr_ratio if expected_language == "ar" else fr_ratio >= ar_ratio


_LANGUAGE_RETRY_SUFFIX = {
    "ar": "\n\nمهم جداً: أجب حصراً باللغة العربية، بدون أي كلمة بلغة أخرى.",
    "fr": "\n\nIMPORTANT : réponds exclusivement en français, sans aucun mot dans une autre langue.",
}

# ============ Métriques Prometheus (réelles) ============
REQUEST_COUNT = Counter("entraide_requests_total", "Nombre de requêtes", ["endpoint", "status"])
REQUEST_LATENCY = Histogram("entraide_request_latency_seconds", "Latence par étape", ["stage"])
CACHE_HIT_COUNT = Counter("entraide_cache_hits_total", "Cache hits")

# ============ Modèles Pydantic ============

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    lang_hint: Optional[str] = None
    use_cache: Optional[bool] = True


class ChatResponse(BaseModel):
    answer: str
    language: str
    intent: str
    sources: List[Dict[str, Any]]
    timings_ms: Dict[str, float]


class HealthResponse(BaseModel):
    status: str
    services: Dict[str, str]


class IngestRequest(BaseModel):
    force_reload: Optional[bool] = False


# ============ App ============

app = FastAPI(
    title="Entraide Nationale — GraphRAG API",
    version="2.0.0",
    description="Router -> Planner -> Executor (Qdrant+Neo4j+Redis) -> Fusion -> Reranker -> Generator -> Guardrail",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Mode admin d'import (squelette de structure, 2026-08-17 — voir
# app/src/admin_import/). Chaque route renvoie 501 tant que le pipeline
# n'est pas implémenté ; inclus dès maintenant pour que le routage/l'auth
# soient déjà en place au moment d'implémenter les handlers.
from src.api.admin_import_routes import router as admin_import_router  # noqa: E402
app.include_router(admin_import_router)

llm_client = LlamaCppClient()
cache = RedisCache()
session_memory = SessionMemory()
graph_search_health = GraphSearch()


def _answer_cache_key(session_id: Optional[str], normalized_query: str, is_followup: bool = False) -> str:
    """Clé de cache réponse (2026-08-15, mémoire conversationnelle) : une
    réponse générée pour une question de suivi elliptique dépend du sujet
    hérité de LA session -- la mettre en cache sous la clé globale (comme
    une question autonome) collisionnerait entre sessions/sujets différents
    ("و ما هي الشروط" seul n'a aucun sens sans son contexte). Les questions
    autonomes gardent la clé globale existante (partageable entre sessions)."""
    if is_followup and session_id:
        return f"{session_id}:{normalized_query}"
    return normalized_query


def _remember_turn(session_id: Optional[str], query: str, intent: str, entities: Optional[Dict[str, Any]], answer: str) -> None:
    session_memory.append_turn(session_id, query, intent, entities or {}, answer)


_FALLBACK_HEADER = {
    "ar": "بناءً على البيانات المتاحة:",
    "fr": "Sur la base des données disponibles :",
}
_FALLBACK_EMPTY = {
    "ar": "لا أتوفر على هذه المعلومة في القاعدة الحالية حالياً.",
    "fr": "Je ne dispose pas de cette information dans la base actuelle.",
}


def _fallback_response(context_json: Dict, language: str = "") -> str:
    """Repli si le guardrail invalide la réponse du LLM : on répond avec le
    contexte structuré brut plutôt que de renvoyer une erreur à l'usager.

    2026-08-16 (bug trouvé en test réel, "corrige le bug du fallback
    FAQ/Programme") : avant, cette fonction n'affichait QUE
    location/conditions -- des champs propres aux résultats de type Centre.
    Pour FAQ (`text` = question+réponse concaténées, voir
    notebooks/02_Chunk.ipynb) et Programme (`budget`), ça produisait une
    liste de titres SANS AUCUN contenu réel -- vérifié en test réel :
    "combien coûte le programme crèches 2027 ?" ne citait jamais les 28M
    MAD pourtant déjà présents dans le contexte récupéré. Affiche
    maintenant `text` (le contenu réel, déjà tronqué par context_builder)
    et `budget` pour tous les types, plus un en-tête localisé (avant :
    bilingue codé en dur même pour une question 100% française, vérifié en
    test réel sur une question AOS en français)."""
    results = context_json.get("results", [])
    if not results:
        return _FALLBACK_EMPTY.get(language, f"{_FALLBACK_EMPTY['ar']} / {_FALLBACK_EMPTY['fr']}")
    header = _FALLBACK_HEADER.get(language, f"{_FALLBACK_HEADER['ar']} / {_FALLBACK_HEADER['fr']}")
    lines = [header, ""]
    for r in results[:3]:
        lines.append(f"- {r['name']} ({r['type']})")
        if r.get("text"):
            lines.append(f"  {r['text']}")
        loc = r.get("location") or {}
        if loc.get("address"):
            lines.append(f"  {loc['address']}")
        if r.get("conditions"):
            lines.append(f"  Conditions: {'; '.join(r['conditions'][:3])}")
        if r.get("documents"):
            lines.append(f"  Documents: {'; '.join(r['documents'][:3])}")
        if r.get("budget"):
            lines.append(f"  Budget: {r['budget']:,.0f} MAD")
    return "\n".join(lines)


_OTHER_RESPONSE = {
    "ar": "مرحباً! أنا المساعد الرسمي للتعاون الوطني. يمكنني مساعدتكم في "
          "التوجيه نحو المراكز والخدمات والبرامج الاجتماعية. ما هو سؤالكم؟",
    "fr": "Bonjour ! Je suis l'assistant officiel de l'Entraide Nationale. "
          "Je peux vous orienter vers les centres, services et programmes "
          "sociaux disponibles. Quelle est votre question ?",
}


def _canned_other_response(language: str) -> str:
    """Salutations / hors-sujet (guide §5.6 intent 'other' : "Réponse courte
    + orientation"). Court-circuite le LLM : une salutation ne justifie pas
    ~100-200s de génération, et le contexte vide n'apporterait rien à un
    vrai LLM call de toute façon (trouvé lors de l'évaluation retrieval :
    "Bonjour, merci beaucoup" déclenchait avant une recherche vectorielle
    complète de 10 résultats sans rapport)."""
    return _OTHER_RESPONSE.get(language, _OTHER_RESPONSE["fr"])


_ABOUT_INSTITUTION_RESPONSE = {
    "ar": "التعاون الوطني مؤسسة عمومية مغربية ذات طابع اجتماعي، تخضع لوصاية "
          "وزارة التضامن والإدماج الاجتماعي والأسرة. تتمثل مهمتها في محاربة "
          "الهشاشة والإقصاء الاجتماعي، من خلال مواكبة الفئات الهشة — الأطفال، "
          "النساء في وضعية صعبة، المسنين، الأشخاص في وضعية إعاقة — عبر شبكة "
          "من المراكز الاجتماعية (حضانات، مراكز تكوين، مؤسسات للحماية "
          "الاجتماعية...) تقدم خدمات وتكوينات وبرامج مواكبة في جميع أنحاء "
          "المغرب.\nيساعدك هذا المساعد على إيجاد المراكز والخدمات والبرامج "
          "التي تهمك — لا تتردد في طرح سؤال محدد.",
    "fr": "L'Entraide Nationale est un établissement public marocain à "
          "caractère social, placé sous la tutelle du Ministère de la "
          "Solidarité, de l'Insertion sociale et de la Famille. Sa mission "
          "est de lutter contre la précarité et l'exclusion sociale, en "
          "accompagnant les populations vulnérables — enfants, femmes en "
          "difficulté, personnes âgées, personnes en situation de handicap "
          "— à travers un réseau de centres sociaux (crèches, centres de "
          "formation, établissements de protection sociale...) proposant "
          "services, formations et programmes d'accompagnement partout au "
          "Maroc.\nCet assistant vous aide à trouver les centres, services "
          "et programmes qui vous concernent — n'hésitez pas à me poser une "
          "question précise.",
}


def _canned_about_institution_response(language: str) -> str:
    """Filet de secours SEULEMENT (2026-08-12) : depuis l'ingestion de
    data_faq (55 FAQ génériques sur la mission de l'Entraide Nationale),
    Intent.ABOUT_INSTITUTION a un vrai outil de recherche (voir
    tool_planner.py) et passe normalement par une génération ancrée sur ce
    contenu. Cette réponse fixe ne sert plus que si la recherche ne trouve
    vraiment rien (Qdrant down, etc.) -- avant cette date, elle était
    utilisée à chaque fois (aucune donnée de ce type n'existait alors)."""
    return _ABOUT_INSTITUTION_RESPONSE.get(language, _ABOUT_INSTITUTION_RESPONSE["fr"])


def _general_knowledge_sync(query: str, language: str) -> tuple:
    """Chemin RELEVANCE GATE -> Not Relevant, version synchrone (/chat).
    Partagé par TOUS les intents de domaine depuis le 2026-08-13 (avant :
    uniquement Intent.OPEN_QUESTION) -- voir le commentaire sur
    OPEN_QUESTION_RELEVANCE_THRESHOLD plus haut. Retourne (texte avec
    disclosure, durée LLM en secondes)."""
    t0 = time.time()
    messages = [
        {"role": "system", "content": GENERAL_KNOWLEDGE_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    response_text = llm_client.chat_completion(messages, max_tokens=GENERAL_KNOWLEDGE_MAX_TOKENS, temperature=0.4)
    if not _language_matches(response_text, language):
        retry_messages = [messages[0], {
            "role": "user",
            "content": query + _LANGUAGE_RETRY_SUFFIX.get(language, ""),
        }]
        response_text = llm_client.chat_completion(retry_messages, max_tokens=GENERAL_KNOWLEDGE_MAX_TOKENS, temperature=0.3)
    disclosure = _GENERAL_KNOWLEDGE_DISCLOSURE.get(language, _GENERAL_KNOWLEDGE_DISCLOSURE["fr"])
    return disclosure + response_text.strip(), time.time() - t0


def _history_block(history: Optional[List[Dict[str, Any]]]) -> str:
    """Bloc "historique récent" injecté dans le prompt (2026-08-15, mémoire
    conversationnelle) -- donne au LLM le sujet des tours précédents pour
    qu'une question de suivi elliptique reste comprise dans son contexte
    réel, sans jamais remplacer la QUESTION actuelle (dernière ligne du
    prompt, seule à laquelle il doit répondre)."""
    if not history:
        return ""
    lines = ["Historique récent de cette conversation (contexte de continuité -- réponds uniquement à la question actuelle ci-dessous, pas à celles de l'historique) :"]
    for turn in history[-2:]:
        if turn.get("query"):
            lines.append(f"- Q: {turn['query']}")
        if turn.get("answer_excerpt"):
            lines.append(f"  R: {turn['answer_excerpt']}")
    return "\n".join(lines) + "\n\n"


def _build_messages(query: str, context_text: str, language: str = "", history: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, str]]:
    user_content = f"{_history_block(history)}Contexte:\n{context_text}\n\nQuestion: {query}"
    # Directive de langue toujours incluse (pas seulement au retry) -- réduit
    # le risque de départ en /chat/stream, où un retry après coup casserait
    # le principe même du streaming (2026-08-13).
    user_content += _LANGUAGE_RETRY_SUFFIX.get(language, "")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ============ /health ============

@app.get("/health", response_model=HealthResponse)
def health():
    services_status = {}

    services_status["llm_vm1"] = "ok" if llm_client.health_check() else "down"

    try:
        cache.client.ping()
        services_status["redis"] = "ok"
    except Exception:
        services_status["redis"] = "down"

    try:
        vector_client = pipeline.vector_search.client
        vector_client.get_collections()
        services_status["qdrant"] = "ok"
    except Exception:
        services_status["qdrant"] = "down"

    try:
        with graph_search_health.driver.session() as session:
            session.run("RETURN 1").single()
        services_status["neo4j"] = "ok"
    except Exception:
        services_status["neo4j"] = "down"

    overall = "healthy" if all(v == "ok" for v in services_status.values()) else "degraded"
    return HealthResponse(status=overall, services=services_status)


# ============ /chat ============

@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_widget_key)])
def chat(request: ChatRequest):
    """Query Preprocessor (normalisation+calculator) -> Router -> [GREETING:
    END | DOMAIN: Planner->Executor->Fusion->Ranking->Reranker->Relevance
    Gate -> (Relevant: Context Builder->Generator->Guardrail | Not relevant:
    General/Fallback)] -> Memory/Cache -> réponse (architecture 2026-08-13)."""
    t0 = time.time()
    try:
        # Query Preprocessor / Normalisation -- avant calculator/routeur,
        # pour que routage, embedding ET clé de cache utilisent la même
        # forme canonique (voir src/tools/text_normalize.py). Le texte
        # ORIGINAL (request.query) reste seul utilisé dans le prompt LLM.
        normalized_query = normalize_query(request.query)

        # Memory / Cache -- vraie réponse finale déjà générée pour cette
        # question EXACTE (texte+langue+intent+sources, pas seulement le
        # contexte de retrieval, voir pipeline.py). 2026-08-13 : avant, ce
        # cache était écrit à chaque réponse mais jamais relu -- une question
        # répétée refaisait tout le LLM (60-160s) à chaque fois. Vérifié
        # avant même le calculator : le coût de ce lookup est négligeable.
        # Mémoire conversationnelle (2026-08-15) : tours récents de CETTE
        # session (voir session_memory.py), utilisés pour (a) essayer d'abord
        # une clé de cache réponse session-scopée avant la clé globale -- une
        # question de suivi elliptique n'a de sens QUE dans cette session --
        # et (b) enrichir le retrieval si la question actuelle s'avère être
        # un suivi (voir pipeline.retrieve::_looks_like_followup).
        history = session_memory.get_history(request.session_id)

        if request.use_cache:
            cache_keys = ([f"{request.session_id}:{normalized_query}"] if request.session_id else []) + [normalized_query]
            cached = None
            for k in cache_keys:
                cached = cache.get(k, query_type="answer")
                if cached:
                    break
            if cached:
                CACHE_HIT_COUNT.inc()
                _remember_turn(request.session_id, request.query, cached["intent"], cached.get("entities"), cached["answer"])
                REQUEST_COUNT.labels(endpoint="/chat", status="200").inc()
                total_ms = (time.time() - t0) * 1000
                return ChatResponse(
                    answer=cached["answer"], language=cached["language"], intent=cached["intent"],
                    sources=cached.get("sources", []),
                    timings_ms={"retrieval": 0.0, "llm": 0.0, "total": round(total_ms, 1)},
                )

        # Calculator : logique métier directe, ni retrieval ni LLM.
        calc = try_calculate(normalized_query)
        if calc:
            calc_language = pipeline.router._detect_language(request.query)
            calc_answer = f"{calc['expression'].strip()} = {calc['result']}"
            _remember_turn(request.session_id, request.query, "calculator", {}, calc_answer)
            REQUEST_COUNT.labels(endpoint="/chat", status="200").inc()
            total_ms = (time.time() - t0) * 1000
            return ChatResponse(
                answer=calc_answer, language=calc_language,
                intent="calculator", sources=[],
                timings_ms={"retrieval": 0.0, "llm": 0.0, "total": round(total_ms, 1)},
            )

        # Router (+ Planner->Executor->Fusion->Ranking->Reranker si le plan
        # de l'intent le prévoit, sinon liste vide -- voir tool_planner.py).
        # Contient aussi le court-circuit "DIRECT ANSWER" (cache hit) de
        # l'architecture : voir src/retrieval/pipeline.py::retrieve.
        retrieval = pipeline.retrieve(request.query, use_cache=request.use_cache, history=history)
        # NB: texte ORIGINAL ici, pas normalized_query -- intent_router.py a
        # des dizaines de patterns ecrits pour le texte arabe BRUT (ة/ى/hamzas
        # non normalises), decouvert casse en test reel le 2026-08-13
        # ("مؤسسة" normalise en "مؤسسه" ne matchait plus aucun pattern ->
        # about_institution jamais detecte). normalized_query reste utilise
        # pour le calculator et la cle de cache reponse (voir plus haut/bas),
        # deux usages ou la normalisation ne risque pas de casser un pattern.
        t_retrieval = time.time()

        if retrieval.get("cache_hit"):
            CACHE_HIT_COUNT.inc()

        intent, language = retrieval["intent"], retrieval["language"]

        # GREETING -> END (pas de recherche par construction, tool_planner
        # donne [] pour "other" -> result_count vaut toujours 0 ici).
        if intent == "other" and retrieval["result_count"] == 0:
            other_answer = _canned_other_response(language)
            _remember_turn(request.session_id, request.query, intent, retrieval.get("entities"), other_answer)
            REQUEST_COUNT.labels(endpoint="/chat", status="200").inc()
            total_ms = (time.time() - t0) * 1000
            return ChatResponse(
                answer=other_answer,
                language=language, intent=intent, sources=[],
                timings_ms={"retrieval": round((t_retrieval - t0) * 1000, 1), "llm": 0.0, "total": round(total_ms, 1)},
            )

        # RELEVANCE GATE (2026-08-13) : généralisée à TOUS les intents de
        # domaine (avant : seulement Intent.OPEN_QUESTION). `result_count`
        # ne peut pas servir de signal ici -- toujours >0 en recherche large
        # (voir OPEN_QUESTION_RELEVANCE_THRESHOLD) -- `reranker_score`
        # (cross-encoder, comparaison sémantique réelle) si.
        context_obj = retrieval["context"]
        relevant = _is_relevant(retrieval)

        if not relevant and intent == "about_institution":
            # Filet dédié plutôt que connaissances générales : une réponse
            # curatée et garantie exacte sur CETTE institution précise vaut
            # mieux qu'une réponse généraliste du LLM qui pourrait halluciner
            # des détails sur un établissement public marocain peu connu.
            about_answer = _canned_about_institution_response(language)
            _remember_turn(request.session_id, request.query, intent, retrieval.get("entities"), about_answer)
            REQUEST_COUNT.labels(endpoint="/chat", status="200").inc()
            total_ms = (time.time() - t0) * 1000
            return ChatResponse(
                answer=about_answer,
                language=language, intent=intent, sources=[],
                timings_ms={"retrieval": round((t_retrieval - t0) * 1000, 1), "llm": 0.0, "total": round(total_ms, 1)},
            )

        if not relevant:
            # Not Relevant -> General/Fallback : connaissances générales du
            # LLM, avec mention explicite que ce n'est PAS issu de la base
            # Entraide Nationale (disclosure préfixée en code, pas laissée à
            # la discrétion du LLM).
            answer_text, llm_s = _general_knowledge_sync(request.query, language)
            gk_entities = retrieval.get("entities")
            if request.use_cache:
                cache_key = _answer_cache_key(request.session_id, normalized_query, retrieval.get("is_followup", False))
                cache.set(cache_key, {"answer": answer_text, "language": language, "intent": intent, "sources": [], "entities": gk_entities}, query_type="answer")
            _remember_turn(request.session_id, request.query, intent, gk_entities, answer_text)
            REQUEST_COUNT.labels(endpoint="/chat", status="200").inc()
            total_ms = (time.time() - t0) * 1000
            return ChatResponse(
                answer=answer_text, language=language, intent=intent, sources=[],
                timings_ms={
                    "retrieval": round((t_retrieval - t0) * 1000, 1),
                    "llm": round(llm_s * 1000, 1),
                    "total": round(total_ms, 1),
                },
            )

        # Relevant -> Context Builder -> Generator -> Guardrail
        guardrail = ResponseGuardrail()
        guardrail.set_context(context_obj["json_context"], expected_language=language)

        messages = _build_messages(request.query, context_obj["text_prompt"], language, history=history)
        response_text = llm_client.chat_completion(messages, max_tokens=GROUNDED_MAX_TOKENS, temperature=0.3)

        is_valid, cleaned_response, issues = guardrail.validate_response(response_text)
        if not is_valid and issues["language_errors"] and not issues["hallucinations"]:
            # Spécifiquement une mauvaise langue (pas une hallucination) :
            # un retry avec directive renforcée donne une vraie réponse dans
            # la bonne langue plutôt que le fallback générique ci-dessous
            # (2026-08-13, "obligatoire de répondre dans la même langue").
            retry_messages = messages[:-1] + [{
                "role": "user",
                "content": messages[-1]["content"] + _LANGUAGE_RETRY_SUFFIX.get(language, ""),
            }]
            response_text = llm_client.chat_completion(retry_messages, max_tokens=GROUNDED_MAX_TOKENS, temperature=0.2)
            is_valid, cleaned_response, issues = guardrail.validate_response(response_text)

        t_llm = time.time()
        if not is_valid:
            cleaned_response = _fallback_response(context_obj["json_context"], language)

        sources = [
            {"type": r["type"], "name": r["name"], "region": r["location"].get("region"),
             "score": r["scores"]["final_score"]}
            for r in context_obj["json_context"]["results"][:CONTEXT_TOP_N_PROMPT]
        ]

        # Memory / Cache
        if request.use_cache:
            cache_key = _answer_cache_key(request.session_id, normalized_query, retrieval.get("is_followup", False))
            cache.set(cache_key, {"answer": cleaned_response, "language": language, "intent": intent, "sources": sources, "entities": retrieval.get("entities")}, query_type="answer")
        _remember_turn(request.session_id, request.query, intent, retrieval.get("entities"), cleaned_response)

        REQUEST_COUNT.labels(endpoint="/chat", status="200").inc()
        total_ms = (time.time() - t0) * 1000
        REQUEST_LATENCY.labels(stage="total").observe(total_ms / 1000)

        return ChatResponse(
            answer=cleaned_response,
            language=language,
            intent=intent,
            sources=sources,
            timings_ms={
                "retrieval": round((t_retrieval - t0) * 1000, 1),
                "llm": round((t_llm - t_retrieval) * 1000, 1),
                "total": round(total_ms, 1),
            },
        )
    except Exception as e:
        REQUEST_COUNT.labels(endpoint="/chat", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


# ============ /chat/stream ============

@app.post("/chat/stream", dependencies=[Depends(require_widget_key)])
def chat_stream(request: ChatRequest):
    """Même pipeline/architecture que /chat (voir sa docstring) — seule la
    génération finale est en SSE."""
    try:
        normalized_query = normalize_query(request.query)
        history = session_memory.get_history(request.session_id)

        # Memory / Cache (voir /chat) -- envoyé en un seul chunk SSE, pas de
        # vrai streaming nécessaire pour une réponse déjà instantanée.
        if request.use_cache:
            cache_keys = ([f"{request.session_id}:{normalized_query}"] if request.session_id else []) + [normalized_query]
            cached = None
            for k in cache_keys:
                cached = cache.get(k, query_type="answer")
                if cached:
                    break
            if cached:
                CACHE_HIT_COUNT.inc()
                _remember_turn(request.session_id, request.query, cached["intent"], cached.get("entities"), cached["answer"])

                def generate_cached():
                    yield f"data: {json.dumps({'chunk': cached['answer']}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'event': 'done', 'sources': cached.get('sources', []), 'intent': cached['intent'], 'language': cached['language']}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                REQUEST_COUNT.labels(endpoint="/chat/stream", status="200").inc()
                return StreamingResponse(generate_cached(), media_type="text/event-stream")

        calc = try_calculate(normalized_query)
        if calc:
            calc_language = pipeline.router._detect_language(request.query)
            calc_text = f"{calc['expression'].strip()} = {calc['result']}"
            _remember_turn(request.session_id, request.query, "calculator", {}, calc_text)

            def generate_calc():
                yield f"data: {json.dumps({'chunk': calc_text}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'event': 'done', 'sources': [], 'intent': 'calculator', 'language': calc_language}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            REQUEST_COUNT.labels(endpoint="/chat/stream", status="200").inc()
            return StreamingResponse(generate_calc(), media_type="text/event-stream")

        retrieval = pipeline.retrieve(request.query, use_cache=request.use_cache, history=history)
        # NB: texte ORIGINAL ici, pas normalized_query -- intent_router.py a
        # des dizaines de patterns ecrits pour le texte arabe BRUT (ة/ى/hamzas
        # non normalises), decouvert casse en test reel le 2026-08-13
        # ("مؤسسة" normalise en "مؤسسه" ne matchait plus aucun pattern ->
        # about_institution jamais detecte). normalized_query reste utilise
        # pour le calculator et la cle de cache reponse (voir plus haut/bas),
        # deux usages ou la normalisation ne risque pas de casser un pattern.
        intent, language = retrieval["intent"], retrieval["language"]

        if intent == "other" and retrieval["result_count"] == 0:
            other_text = _canned_other_response(language)
            _remember_turn(request.session_id, request.query, intent, retrieval.get("entities"), other_text)

            def generate_canned():
                yield f"data: {json.dumps({'chunk': other_text}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'event': 'done', 'sources': [], 'intent': intent, 'language': language}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            REQUEST_COUNT.labels(endpoint="/chat/stream", status="200").inc()
            return StreamingResponse(generate_canned(), media_type="text/event-stream")

        # RELEVANCE GATE (généralisée à tous les intents, voir /chat).
        context_obj = retrieval["context"]
        relevant = _is_relevant(retrieval)

        if not relevant and intent == "about_institution":
            about_text = _canned_about_institution_response(language)
            _remember_turn(request.session_id, request.query, intent, retrieval.get("entities"), about_text)

            def generate_about():
                yield f"data: {json.dumps({'chunk': about_text}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'event': 'done', 'sources': [], 'intent': intent, 'language': language}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            REQUEST_COUNT.labels(endpoint="/chat/stream", status="200").inc()
            return StreamingResponse(generate_about(), media_type="text/event-stream")

        if not relevant:
            gk_entities = retrieval.get("entities")
            gk_is_followup = retrieval.get("is_followup", False)

            def generate_general():
                messages = [
                    {"role": "system", "content": GENERAL_KNOWLEDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": request.query},
                ]
                disclosure = _GENERAL_KNOWLEDGE_DISCLOSURE.get(language, _GENERAL_KNOWLEDGE_DISCLOSURE["fr"])
                yield f"data: {json.dumps({'chunk': disclosure}, ensure_ascii=False)}\n\n"
                full_text = []
                for chunk in llm_client.stream_chat_completion(messages, max_tokens=GENERAL_KNOWLEDGE_MAX_TOKENS, temperature=0.4):
                    full_text.append(chunk)
                    yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
                full_answer = disclosure + "".join(full_text)
                if request.use_cache:
                    cache_key = _answer_cache_key(request.session_id, normalized_query, gk_is_followup)
                    cache.set(cache_key, {"answer": full_answer, "language": language, "intent": intent, "sources": [], "entities": gk_entities}, query_type="answer")
                _remember_turn(request.session_id, request.query, intent, gk_entities, full_answer)
                yield f"data: {json.dumps({'event': 'done', 'sources': [], 'intent': intent, 'language': language}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            REQUEST_COUNT.labels(endpoint="/chat/stream", status="200").inc()
            return StreamingResponse(generate_general(), media_type="text/event-stream")

        messages = _build_messages(request.query, context_obj["text_prompt"], language, history=history)
        sources = [
            {"type": r["type"], "name": r["name"], "score": r["scores"]["final_score"]}
            for r in context_obj["json_context"]["results"][:CONTEXT_TOP_N_PROMPT]
        ]
        grounded_entities = retrieval.get("entities")
        grounded_is_followup = retrieval.get("is_followup", False)

        def generate():
            full_text = []
            for chunk in llm_client.stream_chat_completion(messages, max_tokens=GROUNDED_MAX_TOKENS, temperature=0.3):
                full_text.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            full_answer = "".join(full_text)
            if request.use_cache:
                cache_key = _answer_cache_key(request.session_id, normalized_query, grounded_is_followup)
                cache.set(cache_key, {"answer": full_answer, "language": language, "intent": intent, "sources": sources, "entities": grounded_entities}, query_type="answer")
            _remember_turn(request.session_id, request.query, intent, grounded_entities, full_answer)
            yield f"data: {json.dumps({'event': 'done', 'sources': sources, 'intent': intent, 'language': language}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        REQUEST_COUNT.labels(endpoint="/chat/stream", status="200").inc()
        return StreamingResponse(generate(), media_type="text/event-stream")
    except Exception as e:
        REQUEST_COUNT.labels(endpoint="/chat/stream", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


# ============ Auth admin ============

@app.post("/admin/login")
def admin_login(username: str = Form(...), password: str = Form(...)):
    if not verify_admin_credentials(username, password):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    return {"access_token": create_access_token(username), "token_type": "bearer"}


# ============ /admin/* ============

@app.get("/admin/stats", dependencies=[Depends(require_admin)])
def admin_stats():
    return cache.get_stats()


@app.post("/admin/cache-clear", dependencies=[Depends(require_admin)])
def admin_cache_clear():
    count = cache.clear_pattern("en_cache*")
    return {"status": "cleared", "entries_deleted": count}


# ============ /ingest/* (déclenche réellement les scripts) ============

def _run_script(script_name: str) -> Dict[str, Any]:
    script_path = SCRIPTS_DIR / script_name
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True, text=True, timeout=1800,
    )
    return {"returncode": result.returncode, "stdout_tail": result.stdout[-2000:], "stderr_tail": result.stderr[-2000:]}


@app.post("/ingest/neo4j", dependencies=[Depends(require_admin)])
def ingest_neo4j():
    return _run_script("load_neo4j.py")


@app.post("/ingest/qdrant", dependencies=[Depends(require_admin)])
def ingest_qdrant():
    return _run_script("load_qdrant.py")


# ============ /metrics ============

@app.get("/metrics")
def metrics():
    if not ENABLE_METRICS:
        raise HTTPException(status_code=403, detail="Metrics disabled")
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.on_event("shutdown")
def shutdown_event():
    pipeline.close()
    graph_search_health.close()
    session_memory.close()
