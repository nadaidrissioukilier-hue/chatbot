#!/usr/bin/env python3
"""Diagnostic precis du scoring : trace chaque composante (rrf/offre/geo/
population, penalites EPS/pop) pour comprendre pourquoi un resultat pertinent
arrive bas dans le classement, plutot que de deviner."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from src.routing.intent_router import IntentRouter
from src.planning.tool_planner import ToolPlanner, ToolType
from src.tools.vector_search import VectorSearch
from src.tools.graph_search import GraphSearch
from src.ranking.fusion_ranker import FusionRanker

query = "خدمات لذوي الإعاقة"

router = IntentRouter()
planner = ToolPlanner()
vector_search = VectorSearch()
graph_search = GraphSearch()
fusion_ranker = FusionRanker()

routing = router.route(query)
print(f"intent={routing['intent']} lang={routing['language']} entities={routing['entities']}")

plan = planner.plan(routing["intent"], routing["entities"])
waves = planner.get_execution_order(plan)

vector_results, graph_results = [], []
for wave in waves:
    for tool in wave:
        if tool.tool_type == ToolType.VECTOR_SEARCH:
            vector_results = vector_search.hybrid_search(query, **tool.params)
        elif tool.tool_type == ToolType.GRAPH_EXPANSION:
            seed_ids = [r["entity_id"] for r in vector_results[:5] if r.get("entity_id")]
            print(f"seed_ids (top-5 vector) = {seed_ids}")
            graph_results = graph_search.smart_expansion(seed_ids, tool.params.get("relations", []))

print(f"\n=== Vecteur brut (top 10) ===")
for r in vector_results[:10]:
    p = r["payload"]
    print(f"  {r['entity_id']:20} score={r['score']:.3f} name={p.get('name','')[:40]:40} "
          f"type={p.get('entity_type')} is_eps={p.get('is_eps')} pop={p.get('population_cible','')}")

print(f"\n=== Graphe (expansion) ===")
for r in graph_results[:15]:
    print(f"  {r['id']:20} rel={r['relation_type']:10} score={r['score']:.3f} label={r['label']}")

fused = fusion_ranker.fuse_and_rank(vector_results, graph_results, routing["entities"].get("population_types"))
print(f"\n=== Fusion finale (top 10) ===")
for f in fused[:10]:
    print(f"  {f['entity_id']:20} final={f['final_score']:.3f} rrf={f['rrf_score']:.3f} "
          f"offre={f['offre_score']:.3f} geo={f['geo_score']:.3f} pop={f['population_score']:.3f} "
          f"is_eps={f['is_eps']} has_pop={f['has_population']} mismatch={f.get('population_mismatch')} "
          f"name={f['payload'].get('name','')[:30]}")

# Focus sur شهادة الإعاقة specifiquement
print("\n=== Focus : entités contenant 'شهادة' ===")
for f in fused:
    if "شهادة" in (f["payload"].get("name") or ""):
        print(f"  ID={f['entity_id']}")
        print(f"  payload complet: {f['payload']}")
        print(f"  scores: rrf={f['rrf_score']:.3f} offre={f['offre_score']:.3f} geo={f['geo_score']:.3f} "
              f"pop={f['population_score']:.3f} is_eps={f['is_eps']} has_pop={f['has_population']} "
              f"final={f['final_score']:.3f}")
