"""Reranker avancé avec BGE-Reranker-v2-m3"""
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder
from src.config import RERANKER_MODEL, TOP_K_RERANK, RERANKER_BATCH_SIZE, RERANKER_PRE_FILTER_POOL

class BGEReranker:
    """Cross-encoder reranker pour ranking final"""
    
    def __init__(self):
        self.model = CrossEncoder(RERANKER_MODEL)
    
    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = TOP_K_RERANK
    ) -> List[Dict[str, Any]]:
        """
        Reranke les candidats avec le query
        BGE-Reranker-v2-m3: scores [0, 1] où 1 = très pertinent
        """
        
        if not candidates:
            return []

        # Pré-filtrage par score métier avant le cross-encoder (coûteux sur
        # CPU, ~0.5s/candidat mesuré) : au-delà de RERANKER_PRE_FILTER_POOL,
        # les candidats ont un score fusion trop faible pour raisonnablement
        # remonter dans le top_k final même après reranking sémantique.
        if len(candidates) > RERANKER_PRE_FILTER_POOL:
            candidates = sorted(
                candidates, key=lambda x: x.get("final_score", 0.0), reverse=True
            )[:RERANKER_PRE_FILTER_POOL]

        # Préparer les paires (query, passage)
        passages = [
            self._get_passage_text(c) for c in candidates
        ]
        
        # Récupérer les scores
        scores = self.model.predict(
            [[query, passage] for passage in passages],
            batch_size=RERANKER_BATCH_SIZE
        )
        
        # Ajouter les scores et trier
        for i, candidate in enumerate(candidates):
            candidate["reranker_score"] = float(scores[i])
            # Combiner avec score métier
            candidate["combined_score"] = (
                0.7 * candidate.get("final_score", 0.5) +
                0.3 * scores[i]
            )
        
        # Trier et limiter
        ranked = sorted(candidates, key=lambda x: x["combined_score"], reverse=True)
        
        return ranked[:top_k]
    
    def _get_passage_text(self, candidate: Dict) -> str:
        """Extrait le texte du candidat pour reranking"""
        payload = candidate.get("payload", {})
        
        # Prioriser: text > description > name
        text = payload.get("text")
        if text:
            return text[:500]  # Limiter la longueur
        
        description = payload.get("description")
        if description:
            return description[:500]
        
        name = payload.get("name", "")
        if name:
            return name
        
        return str(payload)[:500]
