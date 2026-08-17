#!/usr/bin/env python3
"""Ré-embed data/chunks/chunks_all.jsonl -> data/embeddings/embeddings_all.jsonl
SANS ré-encoder les chunks deja embeddes (04_Embed.ipynb re-encode tout a
chaque run -- mesure ~60-90 min sur ce CPU partage pour ~10k chunks, cf
README.md. Un ajout de quelques centaines de chunks (data_faq) ne justifie
pas de tout refaire).

- Dense (BGE-M3) : seulement pour les chunk_id absents de l'ancien
  embeddings_all.jsonl.
- Sparse (TF-IDF hashe) : recalcule pour TOUT le corpus (l'IDF change avec
  le corpus, mais c'est un calcul Python pur, rapide -- pas de modele).

Usage: .venv/bin/python3 scripts/embed_incremental.py
"""
import os
import sys
import time
from pathlib import Path

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"

UNIT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UNIT_DIR / "notebooks"))

from etl_lib.io_utils import load_jsonl, save_jsonl  # noqa: E402
from etl_lib.sparse_vectorizer import SparseVectorizer  # noqa: E402

CHUNKS_DIR = UNIT_DIR / "data" / "chunks"
EMBEDDINGS_DIR = UNIT_DIR / "data" / "embeddings"


def main():
    chunks = load_jsonl(CHUNKS_DIR / "chunks_all.jsonl")
    old_records = {r["id"]: r for r in load_jsonl(EMBEDDINGS_DIR / "embeddings_all.jsonl")}
    print(f"Chunks (total)        : {len(chunks)}")
    print(f"Embeddings existants   : {len(old_records)}")

    new_chunks = [c for c in chunks if c["chunk_id"] not in old_records]
    print(f"Chunks a embedder (nouveaux) : {len(new_chunks)}")

    if new_chunks:
        import torch
        torch.set_num_threads(4)
        from sentence_transformers import SentenceTransformer

        EMBEDDING_MODEL = "BAAI/bge-m3"
        t0 = time.time()
        model = SentenceTransformer(EMBEDDING_MODEL)
        print(f"Modele charge en {time.time()-t0:.0f}s")

        texts = [c["text_bilingual"] for c in new_chunks]
        vecs = model.encode(texts, batch_size=32, normalize_embeddings=True)
        print(f"{len(vecs)} nouveaux vecteurs denses generes en {time.time()-t0:.1f}s")

        for c, v in zip(new_chunks, vecs):
            old_records[c["chunk_id"]] = {"id": c["chunk_id"], "vector": v.tolist(), "_chunk": c}

    # Recalcule le sparse (IDF + vecteurs) sur le corpus complet -- rapide
    # (pas de modele), et necessaire car l'IDF depend du corpus entier.
    chunk_by_id = {c["chunk_id"]: c for c in chunks}
    all_texts_ordered = [chunk_by_id[cid]["text_bilingual"] for cid in chunk_by_id]
    idf = SparseVectorizer.fit_idf(all_texts_ordered)
    vectorizer = SparseVectorizer(idf)
    vectorizer.save(EMBEDDINGS_DIR / "sparse_idf.json")
    print(f"IDF recalcule sur {len(all_texts_ordered)} textes -> {len(idf)} termes")

    records = []
    for chunk_id, chunk in chunk_by_id.items():
        prior = old_records.get(chunk_id)
        if prior is None:
            raise RuntimeError(f"Chunk sans vecteur dense: {chunk_id} (ne devrait pas arriver)")
        sp_idx, sp_val = vectorizer.vectorize(chunk["text_bilingual"])
        records.append({
            "id": chunk_id,
            "vector": prior["vector"],
            "sparse_indices": sp_idx,
            "sparse_values": sp_val,
            "payload": {
                "text": chunk["text_bilingual"][:500],
                "entity_type": chunk["entity_type"],
                "entity_id": chunk["entity_id"],
                "type": chunk["type"],
                "chunk_type": chunk["chunk_type"],
                "langue": chunk["langue"],
                "population_cible": chunk.get("population_cible", ""),
                "institutions": chunk.get("institutions", []),
            },
        })

    save_jsonl(EMBEDDINGS_DIR / "embeddings_all.jsonl", records)
    size_mb = (EMBEDDINGS_DIR / "embeddings_all.jsonl").stat().st_size / 1024 / 1024
    print(f"\n✅ embeddings_all.jsonl : {len(records)} vecteurs, {size_mb:.1f} Mo "
          f"({len(new_chunks)} nouveaux dense, {len(records)} sparse recalcules)")


if __name__ == "__main__":
    main()
