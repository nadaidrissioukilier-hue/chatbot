"""Recherche vectorielle hybride réelle : dense (BGE-M3) + sparse (TF-IDF
hashé) fusionnés côté serveur par Qdrant (RRF natif), dans une seule
collection à vecteurs nommés.

Corrige 3 bugs v1 :
- modèle d'embedding au moment de la requête (MiniLM 384D) différent du
  modèle utilisé à l'indexation (BGE-M3 1024D) -> recherche vectorielle
  cassée. Le modèle est maintenant lu depuis la même config que
  scripts/load_qdrant.py (source unique de vérité).
- collection Qdrant incohérente avec celle réellement indexée.
- recherche sparse factice (vecteur nul contre une collection inexistante)
  -> vrai vecteur sparse, même vectoriseur qu'à l'indexation.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Prefetch, FusionQuery, Fusion, SparseVector, Filter, FieldCondition, MatchAny,
)

from src.config import (
    QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION,
    QDRANT_DENSE_VECTOR_NAME, QDRANT_SPARSE_VECTOR_NAME,
    EMBEDDING_MODEL, TOP_K_DENSE, TOP_K_SPARSE, EMBEDDINGS_DIR,
)
from src.tools.sparse_vectorizer import SparseVectorizer

SPARSE_IDF_PATH = EMBEDDINGS_DIR / "sparse_idf.json"


class VectorSearch:
    def __init__(self):
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)
        self.sparse_vectorizer = SparseVectorizer.load(SPARSE_IDF_PATH)
        self.collection = QDRANT_COLLECTION

    def _build_filter(
        self,
        entity_types: Optional[List[str]] = None,
        institution_filter: Optional[List[str]] = None,
    ) -> Optional[Filter]:
        # NB: pas de filtre géographique ici (volontaire). Un test réel a montré
        # que les entités géo extraites de la question (ex: "سلا" en arabe) ne
        # correspondent presque jamais littéralement à payload["region"], qui est
        # au format administratif français (ex: "Rabat-Salé-Kénitra") -> un filtre
        # dur ici élimine tous les résultats au lieu de les prioriser. La
        # géographie est prise en compte comme signal (pas comme filtre bloquant)
        # via graph_search.expand_geo + fusion_ranker.geo_score.
        must = []
        if entity_types:
            must.append(FieldCondition(key="entity_type", match=MatchAny(any=entity_types)))
        if institution_filter:
            must.append(FieldCondition(key="institutions", match=MatchAny(any=institution_filter)))
        return Filter(must=must) if must else None

    def hybrid_search(
        self,
        query: str,
        top_k_dense: int = TOP_K_DENSE,
        top_k_sparse: int = TOP_K_SPARSE,
        entity_types: Optional[List[str]] = None,
        geo_filter: Optional[List[str]] = None,
        institution_filter: Optional[List[str]] = None,
        limit: int = 50,
        **_ignored,
    ) -> List[Dict[str, Any]]:
        """Recherche hybride dense+sparse avec fusion RRF native Qdrant."""
        dense_vector = self.embedder.encode(query, normalize_embeddings=True).tolist()
        sparse_indices, sparse_values = self.sparse_vectorizer.vectorize(query)
        query_filter = self._build_filter(entity_types, institution_filter)

        prefetch = [
            Prefetch(query=dense_vector, using=QDRANT_DENSE_VECTOR_NAME, limit=top_k_dense, filter=query_filter),
        ]
        if sparse_indices:
            prefetch.append(Prefetch(
                query=SparseVector(indices=sparse_indices, values=sparse_values),
                using=QDRANT_SPARSE_VECTOR_NAME, limit=top_k_sparse, filter=query_filter,
            ))

        results = self.client.query_points(
            collection_name=self.collection,
            prefetch=prefetch,
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit,
            with_payload=True,
        )

        return [
            {
                "id": str(point.id),
                "entity_id": point.payload.get("entity_id"),
                "score": point.score,
                "rank": i + 1,
                "method": "hybrid_rrf",
                "payload": point.payload,
            }
            for i, point in enumerate(results.points)
        ]
