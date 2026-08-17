"""Fusion/Ranking : combine vector + graph, applique la formule métier.

Corrige le bug v1 : la pénalité EPS et le score population lisaient des clés
(`payload["type"] == "EPS"`, `payload["population_type"]`) qui n'existent pas
dans le payload réel -> code mort, la règle métier ne se déclenchait jamais.
Les clés utilisées ici (`is_eps`, `institutions`, `population_cible`) sont
celles réellement écrites par scripts/load_qdrant.py.

Fusionne maintenant sur `entity_id` (l'ID métier partagé Neo4j<->Qdrant),
pas sur l'ID de point Qdrant (qui n'a pas de sens côté graphe).
"""
from typing import List, Dict, Any, Optional
from src.config import (
    WEIGHT_RRF, WEIGHT_OFFRE, WEIGHT_POPULATION, WEIGHT_GEO,
    PENALTY_EPS, PENALTY_NO_POP, PENALTY_POP_MISMATCH, POPULATION_CIBLES,
    BOOST_FAQ_QUESTION_MATCH, FAQ_QUESTION_MATCH_RANK_THRESHOLD,
)


class FusionRanker:
    """Score = 0.35*RRF + 0.25*OFFRE + 0.25*population + 0.15*géo, avec
    pénalités EPS (x0.70), population manquante (x0.85) et population
    en contradiction explicite avec la demande (x0.55)."""

    def fuse_and_rank(
        self,
        vector_results: List[Dict],
        graph_results: List[Dict],
        requested_populations: Optional[List[str]] = None,
    ) -> List[Dict]:
        requested_populations = requested_populations or []
        combined: Dict[str, Dict[str, Any]] = {}

        rrf_scores = self._normalize({str(r["entity_id"]): r["score"] for r in vector_results if r.get("entity_id")})

        # Question quasi-identique (chunk_type=faq_question) parmi les
        # meilleurs rangs vectoriels bruts -> signal fort de "c'est la même
        # question, pas juste un sujet proche". Calculé sur TOUS les
        # vector_results (indépendant des écrasements par entity_id
        # ci-dessous, qui ne gardent qu'un seul chunk par entité).
        faq_question_hit_ids = {
            str(r["entity_id"])
            for r in vector_results
            if r.get("entity_id")
            and r.get("payload", {}).get("chunk_type") == "faq_question"
            and r.get("rank", 999) <= FAQ_QUESTION_MATCH_RANK_THRESHOLD
        }

        for item in vector_results:
            entity_id = item.get("entity_id")
            if not entity_id:
                continue
            payload = item.get("payload", {})
            combined[entity_id] = {
                "entity_id": entity_id,
                "payload": payload,
                "rrf_score": rrf_scores.get(entity_id, 0.0),
                "offre_score": 0.0,
                "geo_score": 0.0,
                "population_score": 0.0,
                "population_mismatch": False,
                "source_vector": True,
                "source_graph": False,
                "is_eps": bool(payload.get("is_eps", False)),
                "has_population": bool(payload.get("population_cible")),
            }

        offre_raw, geo_raw = {}, {}
        for item in graph_results:
            entity_id = item.get("id")
            if not entity_id:
                continue
            rel_type = item.get("relation_type")
            data = item.get("data", {})

            if entity_id not in combined:
                combined[entity_id] = {
                    "entity_id": entity_id,
                    "payload": self._data_to_payload(item.get("label"), data),
                    "rrf_score": 0.0, "offre_score": 0.0, "geo_score": 0.0, "population_score": 0.0,
                    "population_mismatch": False,
                    "source_vector": False, "source_graph": True,
                    "is_eps": "EPS" in (data.get("institutions") or []),
                    "has_population": False,
                }
            else:
                combined[entity_id]["source_graph"] = True

            if rel_type == "offre":
                offre_raw[entity_id] = max(offre_raw.get(entity_id, 0), item.get("score", 0))
            elif rel_type == "geo":
                geo_raw[entity_id] = max(geo_raw.get(entity_id, 0), item.get("score", 0))
            elif rel_type == "cible":
                combined[entity_id]["population_score"] = 1.0
                combined[entity_id]["has_population"] = True

        offre_norm = self._normalize(offre_raw)
        geo_norm = self._normalize(geo_raw)
        for entity_id, score in offre_norm.items():
            combined[entity_id]["offre_score"] = score
        for entity_id, score in geo_norm.items():
            combined[entity_id]["geo_score"] = score

        # Correspondance population par texte (signal doux, en plus du graphe)
        if requested_populations:
            requested_ar = [POPULATION_CIBLES.get(p, {}).get("ar", "") for p in requested_populations]
            for item in combined.values():
                pop_text = (item["payload"].get("population_cible") or "")
                matches = (
                    any(ar and ar in pop_text for ar in requested_ar)
                    or any(p in pop_text.lower() for p in requested_populations)
                )
                if matches:
                    item["population_score"] = max(item["population_score"], 0.8)
                    item["has_population"] = True
                elif pop_text.strip():
                    # population_cible renseignée mais différente de celle
                    # demandée -> contradiction explicite, pas une simple
                    # absence de signal (voir PENALTY_POP_MISMATCH dans config.py).
                    item["population_mismatch"] = True

        for entity_id, item in combined.items():
            base_score = (
                WEIGHT_RRF * item["rrf_score"]
                + WEIGHT_OFFRE * item["offre_score"]
                + WEIGHT_POPULATION * item["population_score"]
                + WEIGHT_GEO * item["geo_score"]
            )
            final_score = base_score
            item["faq_question_match"] = entity_id in faq_question_hit_ids
            if item["faq_question_match"]:
                final_score *= BOOST_FAQ_QUESTION_MATCH
            if item["is_eps"]:
                final_score *= PENALTY_EPS
            if item["population_mismatch"]:
                final_score *= PENALTY_POP_MISMATCH
            elif not item["has_population"]:
                final_score *= PENALTY_NO_POP
            item["final_score"] = final_score

        return sorted(combined.values(), key=lambda x: x["final_score"], reverse=True)

    def _data_to_payload(self, label: str, data: Dict) -> Dict:
        """Normalise un nœud Neo4j brut vers la même forme que le payload Qdrant."""
        payload = dict(data)
        payload.setdefault("entity_type", label)
        payload.setdefault("name", data.get("nom") or data.get("service_fr") or data.get("titre_fr") or "")
        payload.setdefault("region", data.get("region", ""))
        payload.setdefault("address", data.get("adresse", ""))
        payload.setdefault("population_cible", data.get("population_cible_ar") or data.get("personnes_cibles", ""))
        return payload

    def _normalize(self, scores: Dict[str, float]) -> Dict[str, float]:
        if not scores:
            return {}
        max_score = max(scores.values()) or 1.0
        return {k: v / max_score for k, v in scores.items()}
