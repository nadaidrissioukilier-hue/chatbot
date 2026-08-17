"""Pipeline de retrieval partagé entre /chat et /chat/stream.

La v1 avait deux implémentations divergentes : /chat faisait le retrieval
complet, /chat/stream envoyait la question brute au LLM sans passer par
Qdrant/Neo4j (pas de RAG du tout en streaming). Un seul pipeline ici,
partagé — seule la génération finale diffère (synchrone vs SSE).
"""
from typing import Dict, Any, List, Optional

from src.routing.intent_router import IntentRouter
from src.planning.tool_planner import ToolPlanner, ToolType
from src.tools.vector_search import VectorSearch
from src.tools.graph_search import GraphSearch
from src.tools.geo_resolver import resolve_regions
from src.tools.redis_cache import RedisCache
from src.ranking.fusion_ranker import FusionRanker
from src.ranking.reranker import BGEReranker
from src.generation.context_builder import ContextBuilder

router = IntentRouter()
planner = ToolPlanner()
vector_search = VectorSearch()
graph_search = GraphSearch()
cache = RedisCache()
fusion_ranker = FusionRanker()
reranker = BGEReranker()
context_builder = ContextBuilder()


def _looks_like_followup(query: str, entities: Dict[str, Any]) -> bool:
    """Signal "question de suivi elliptique" (2026-08-15) : question courte
    ET qui n'a fait remonter AUCUNE entité propre (population/institution/
    région) -- cf. cas réel "و ما هي الشروط والوثائق المطلوبة" (5 mots, 0
    entité) après une question sur "الترويض الحركي" (rééducation motrice,
    CPSH). Une question longue ou déjà bien ancrée dans une entité propre
    n'a pas besoin d'hériter du tour précédent."""
    has_own_entities = bool(
        entities.get("population_types") or entities.get("institutions") or entities.get("regions")
    )
    return (not has_own_entities) and len(query.split()) <= 8


def _merge_entities(previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    merged = {}
    for key in ("population_types", "institutions", "regions"):
        merged[key] = list(dict.fromkeys((current.get(key) or []) + (previous.get(key) or [])))
    return merged


def retrieve(query: str, use_cache: bool = True, history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Exécute Router -> Planner -> Executor (Qdrant+Neo4j+Redis) -> Fusion
    -> Reranker -> Context Builder. Retourne tout ce qu'il faut pour générer
    la réponse et pour peupler /chat et /chat/stream de façon identique.

    `history` (2026-08-15, mémoire conversationnelle, voir session_memory.py)
    : derniers tours de LA MÊME session. Si la question actuelle ressemble à
    un suivi elliptique (_looks_like_followup), le sujet du tour précédent
    est hérité pour le retrieval (search_query enrichie, entités fusionnées)
    -- SANS changer `query` elle-même, qui reste le texte affiché/cité et
    envoyé tel quel au LLM (voir main.py::_build_messages)."""

    routing_result = router.route(query)
    intent = routing_result["intent"]
    language = routing_result["language"]
    entities = routing_result["entities"]

    search_query = query
    is_followup = False
    if history and _looks_like_followup(query, entities):
        last_turn = history[-1]
        search_query = f"{last_turn.get('query', '')} {query}".strip()
        entities = _merge_entities(last_turn.get("entities", {}) or {}, entities)
        is_followup = True

    cache_key_type = f"{intent}:{language}"
    if use_cache:
        cached = cache.get(search_query, query_type=cache_key_type)
        if cached:
            return {**cached, "cache_hit": True, "intent": intent, "language": language, "is_followup": is_followup}

    tool_plan = planner.plan(intent, entities)
    execution_waves = planner.get_execution_order(tool_plan)

    vector_results, graph_results = [], []
    for wave in execution_waves:
        for tool in wave:
            if tool.tool_type == ToolType.VECTOR_SEARCH:
                vector_results = vector_search.hybrid_search(search_query, **tool.params)
            elif tool.tool_type == ToolType.GRAPH_EXPANSION:
                # Seeds = entity_id métier (clé partagée Neo4j<->Qdrant), pas l'ID de point Qdrant
                seed_ids = [r["entity_id"] for r in vector_results[:5] if r.get("entity_id")]
                if seed_ids:
                    graph_results = graph_search.smart_expansion(
                        seed_ids, tool.params.get("relations", []),
                        filters={k: v for k, v in tool.params.items() if k.endswith("_filter")},
                    )

    # Ancrage géographique DIRECT (2026-08-14) : indépendant du plan d'outils
    # de l'intent et de ce que la recherche vectorielle a trouvé en premier
    # -- dès qu'une ville/région reconnue est mentionnée, les centres de
    # CETTE région exacte sont injectés comme candidats avec un signal geo
    # fort, plutôt que de dépendre uniquement du voisinage d'un centre déjà
    # trouvé (expand_geo, qui rate la bonne région si aucun résultat
    # vectoriel initial n'y était -- cas réel : "...أسكن بالرباط" ne
    # remontait qu'un seul centre pertinent, le reste dispersé ailleurs).
    for region in resolve_regions(entities.get("regions")):
        region_results = graph_search.expand_by_region(region, population_types=entities.get("population_types"))
        existing_ids = {r["id"] for r in graph_results}
        graph_results.extend(r for r in region_results if r["id"] not in existing_ids)

    fused = fusion_ranker.fuse_and_rank(vector_results, graph_results, entities.get("population_types"))
    reranked = reranker.rerank(search_query, fused)
    context_obj = context_builder.build_context(search_query, reranked)

    result = {
        "intent": intent,
        "language": language,
        "entities": entities,
        "context": context_obj,
        "result_count": len(reranked),
        "cache_hit": False,
        "is_followup": is_followup,
        "search_query": search_query,
    }

    if use_cache:
        cache.set(search_query, {
            "intent": intent, "language": language, "entities": entities,
            "context": context_obj, "result_count": len(reranked), "is_followup": is_followup,
            "search_query": search_query,
        }, query_type=cache_key_type)

    return result


def close():
    graph_search.close()
    cache.close()
