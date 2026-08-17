"""Context Builder : construit le contexte riche pour le LLM.

Corrige le bug v1 : le payload Qdrant réel ne contenait que
text/entity_type/entity_id/type, alors que ce module lisait name/region/
address/phone/services/target_population -> contexte transmis au LLM
quasi vide. Lit maintenant les champs réellement écrits par
scripts/load_qdrant.py (name, region, address, institutions,
population_cible, conditions, documents, budget...).
"""
from typing import List, Dict, Any
from datetime import datetime, timezone

from src.config import CONTEXT_TOP_N_PROMPT, CONTEXT_TEXT_TRUNCATE, CONTEXT_FIELD_TRUNCATE


class ContextBuilder:
    def build_context(self, query: str, ranked_results: List[Dict]) -> Dict[str, Any]:
        structured = self._structure_results(ranked_results)
        prompt_text = self._generate_prompt(query, structured)

        context_json = {
            "query": query,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result_count": len(ranked_results),
            "results": structured,
            "metadata": self._extract_metadata(ranked_results),
        }
        return {"json_context": context_json, "text_prompt": prompt_text, "raw_results": ranked_results}

    def _structure_results(self, results: List[Dict]) -> List[Dict]:
        structured = []
        for i, result in enumerate(results):
            payload = result.get("payload", {})
            structured.append({
                "rank": i + 1,
                "entity_id": result.get("entity_id"),
                "type": payload.get("entity_type", "unknown"),
                "name": payload.get("name", ""),
                "text": self._truncate(payload.get("text", ""), CONTEXT_TEXT_TRUNCATE),
                "location": {
                    "region": payload.get("region"),
                    "delegation": payload.get("delegation"),
                    "commune": payload.get("commune"),
                    "address": payload.get("address"),
                },
                "institutions": payload.get("institutions", []),
                "population_cible": payload.get("population_cible", ""),
                # 2026-08-13 ("donner le max de text data") : relevé de
                # 3x180 à 5xCONTEXT_FIELD_TRUNCATE -- un contexte plus riche
                # coûte en latence (prompt plus long, voir config.py) mais
                # c'est le compromis explicitement demandé.
                "conditions": [self._truncate(c, CONTEXT_FIELD_TRUNCATE) for c in payload.get("conditions", [])[:5]],
                "documents": [self._truncate(d, CONTEXT_FIELD_TRUNCATE) for d in payload.get("documents", [])[:5]],
                "budget": payload.get("budget"),
                "is_eps": payload.get("is_eps", False),
                "scores": {
                    "final_score": round(result.get("final_score", 0), 3),
                    "reranker_score": round(result.get("reranker_score", 0), 3),
                    "combined_score": round(result.get("combined_score", 0), 3),
                },
                "sources": {
                    "source_vector": result.get("source_vector", False),
                    "source_graph": result.get("source_graph", False),
                },
            })
        return structured

    def _generate_prompt(self, query: str, structured_results: List[Dict]) -> str:
        lines = [
            "Contexte pour Entraide Nationale (Maroc):",
            f"Question utilisateur: {query}",
            f"Nombre de résultats pertinents: {len(structured_results)}\n",
            "Résultats:",
        ]
        for r in structured_results[:CONTEXT_TOP_N_PROMPT]:
            lines.append(f"\n#{r['rank']} - {r['type'].upper()} - {r['name']}")
            if r["text"]:
                lines.append(f"Détail: {r['text']}")
            loc = r["location"]
            if loc.get("address") or loc.get("commune"):
                loc_str = ", ".join(v for v in [loc.get("address"), loc.get("commune"), loc.get("region")] if v)
                lines.append(f"Localisation: {loc_str}")
            if r["institutions"]:
                lines.append(f"Institution(s): {', '.join(r['institutions'])}" + (" (dernier recours)" if r["is_eps"] else ""))
            if r["population_cible"]:
                lines.append(f"Public cible: {r['population_cible']}")
            if r["conditions"]:
                lines.append(f"Conditions: {'; '.join(r['conditions'])}")
            if r["documents"]:
                lines.append(f"Documents requis: {'; '.join(r['documents'])}")
            if r["budget"]:
                lines.append(f"Budget programme: {r['budget']:,.0f} MAD")

        lines.extend([
            "\n\nInstructions:",
            "1. Répondez dans la langue de la question (arabe ou français)",
            # 2026-08-13 ("donner le max de text data") : avant "Soyez concis,
            # priorité aux 3 meilleurs résultats" -- inversé, la demande
            # explicite est maintenant la complétude, pas la brièveté.
            "2. Soyez complet et détaillé : couvrez CHAQUE résultat pertinent ci-dessus "
            "(pas seulement le premier), avec ses conditions, documents et institutions propres",
            "3. Structurez par catégorie/résultat (ex: une section par population ou par centre) si plusieurs s'appliquent",
            "4. Si un résultat est marqué 'dernier recours', ne le proposer qu'en l'absence d'alternative",
            "5. Pas d'hallucination: uniquement les données du contexte ci-dessus",
        ])
        return "\n".join(lines)

    def _extract_metadata(self, results: List[Dict]) -> Dict[str, Any]:
        types, regions, populations = set(), set(), set()
        for r in results:
            payload = r.get("payload", {})
            if payload.get("entity_type"):
                types.add(payload["entity_type"])
            if payload.get("region"):
                regions.add(payload["region"])
            if payload.get("population_cible"):
                populations.add(payload["population_cible"])
        return {
            "result_types": list(types),
            "regions_covered": list(regions),
            "populations_targeted": list(populations),
            "avg_score": round(sum(r.get("final_score", 0) for r in results) / len(results), 3) if results else 0,
        }

    def _truncate(self, text: str, max_len: int) -> str:
        if not text:
            return ""
        return text[:max_len] + "..." if len(text) > max_len else text
