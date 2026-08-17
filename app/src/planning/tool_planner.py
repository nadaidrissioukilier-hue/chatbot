"""Planner: construit le plan d'outils selon l'intent.

Corrige le bug v1 : les noms de relations demandés ici (LOCALISE_DANS,
OFFRE_SERVICE, OFFRE_PAR, IMPLIQUE...) ne correspondaient à AUCUNE relation
réellement présente dans le graphe (OFFRE, CIBLE, DANS, ABRITE_DANS,
S_APPUIE_SUR) ni aux noms reconnus par graph_search.py -> toute expansion de
graphe retournait zéro résultat, silencieusement. Alignés ici sur le schéma
réel (voir scripts/load_neo4j.py).
"""
from typing import Dict, List, Any
from dataclasses import dataclass
from enum import Enum


class ToolType(str, Enum):
    VECTOR_SEARCH = "vector_search"
    GRAPH_EXPANSION = "graph_expansion"
    CACHE_CHECK = "cache_check"


@dataclass
class ToolCall:
    tool_type: ToolType
    params: Dict[str, Any]
    priority: int  # 1=haute, 2=moyenne, 3=basse
    fallback: bool = False


class ToolPlanner:
    """Construit le plan d'exécution d'outils, noms de relations = schéma réel."""

    def __init__(self):
        self.intent_to_tools = {
            "centre_search": [
                ToolCall(ToolType.CACHE_CHECK, {"query_type": "centre"}, priority=1),
                ToolCall(ToolType.VECTOR_SEARCH, {"entity_types": ["Centre"]}, priority=1),
                ToolCall(ToolType.GRAPH_EXPANSION, {"relations": ["ABRITE_DANS", "OFFRE"], "depth": 1}, priority=2),
            ],
            "service_search": [
                ToolCall(ToolType.CACHE_CHECK, {"query_type": "service"}, priority=1),
                # "FAQ" et "Institution" ajoutés (2026-08-12) suite à
                # l'ingestion de data_faq (121 FAQ + 8 profils Institution) :
                # beaucoup de ces questions sont formulées comme du
                # service_search classique ("conditions pour...") plutôt que
                # détectées comme faq_search -> sans ça, ce contenu n'était
                # trouvable qu'à travers le seul intent faq_search, trop étroit.
                ToolCall(ToolType.VECTOR_SEARCH, {"entity_types": ["Service", "Centre", "FAQ", "Institution"]}, priority=1),
                ToolCall(ToolType.GRAPH_EXPANSION, {"relations": ["OFFRE", "CIBLE"], "depth": 1}, priority=2),
            ],
            "faq_search": [
                ToolCall(ToolType.CACHE_CHECK, {"query_type": "faq"}, priority=1),
                ToolCall(ToolType.VECTOR_SEARCH, {"entity_types": ["FAQ"]}, priority=1),
                ToolCall(ToolType.GRAPH_EXPANSION, {"relations": ["REPOND_A"], "depth": 1}, priority=2),
            ],
            "programme_2027": [
                ToolCall(ToolType.CACHE_CHECK, {"query_type": "programme"}, priority=1),
                ToolCall(ToolType.VECTOR_SEARCH, {"entity_types": ["Programme"]}, priority=1),
                ToolCall(ToolType.GRAPH_EXPANSION, {"relations": ["S_APPUIE_SUR", "CIBLE"], "depth": 1}, priority=2),
            ],
            # "other" = salutations / hors-sujet (guide : "Réponse courte +
            # orientation"). Volontairement AUCUN outil : lancer une recherche
            # vectorielle complète pour "Bonjour" coûte ~20-40s pour rien et
            # peut injecter un contexte non pertinent dans la réponse (trouvé
            # lors de l'évaluation retrieval : "Bonjour, merci beaucoup" ->
            # 10 résultats sans rapport). Court-circuité en réponse canned
            # dans l'API (voir main.py::_canned_other_response).
            "other": [],
            # Questions méta sur l'institution elle-même ("c'est quoi
            # l'entraide nationale ?", "ما هي مؤسسة التعاون الوطني") :
            # DEPUIS l'ingestion de data_faq (2026-08-12, 55 FAQ génériques
            # sur la mission/les objectifs de l'Entraide Nationale), cette
            # donnée existe réellement -> vraie recherche (avant : aucun
            # outil, court-circuité en texte fixe -- gardé dans main.py
            # UNIQUEMENT comme filet de secours si result_count reste à 0
            # malgré la recherche).
            "about_institution": [
                ToolCall(ToolType.CACHE_CHECK, {"query_type": "about_institution"}, priority=1),
                ToolCall(ToolType.VECTOR_SEARCH, {"entity_types": ["FAQ"]}, priority=1),
            ],
            # Question réelle mais hors des patterns de domaine connus
            # (2026-08-12, voir Intent.OPEN_QUESTION) : recherche large, sans
            # filtre entity_type -- si quelque chose de pertinent existe
            # malgré l'échec du pattern matching, la génération doit rester
            # ancrée dessus (voir main.py) plutôt que de basculer à tort en
            # mode "connaissances générales".
            "open_question": [
                ToolCall(ToolType.CACHE_CHECK, {"query_type": "open_question"}, priority=1),
                ToolCall(ToolType.VECTOR_SEARCH, {}, priority=1),
            ],
        }

    def plan(self, intent: str, entities: Dict[str, List[str]]) -> List[ToolCall]:
        base_tools = self.intent_to_tools.get(intent, self.intent_to_tools["other"])
        adapted_tools = self._adapt_tools(base_tools, entities)
        adapted_tools.sort(key=lambda x: x.priority)
        return adapted_tools

    def _adapt_tools(self, tools: List[ToolCall], entities: Dict[str, List[str]]) -> List[ToolCall]:
        adapted = []
        for tool in tools:
            adapted_tool = ToolCall(
                tool_type=tool.tool_type,
                params=dict(tool.params),
                priority=tool.priority,
                fallback=tool.fallback,
            )
            if entities.get("population_types"):
                adapted_tool.params["population_filter"] = entities["population_types"]
            if entities.get("regions"):
                adapted_tool.params["geo_filter"] = entities["regions"]
            if entities.get("institutions"):
                adapted_tool.params["institution_filter"] = entities["institutions"]
            adapted.append(adapted_tool)
        return adapted

    def get_execution_order(self, tools: List[ToolCall]) -> List[List[ToolCall]]:
        from collections import defaultdict
        groups = defaultdict(list)
        for tool in tools:
            groups[tool.priority].append(tool)
        return [groups[p] for p in sorted(groups.keys())]
