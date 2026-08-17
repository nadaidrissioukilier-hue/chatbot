"""Pipeline d'import admin : ingère n'importe quel JSON question/réponse
(forme et noms de champs inconnus a priori) de façon incrémentale, sans
jamais vider/recréer les données existantes (Neo4j: MERGE uniquement,
Qdrant: upsert uniquement).

Voir docs/admin_import_schema.md pour le schéma attendu et le plan complet
(discussion produit du 2026-08-17).

Étapes du pipeline (dans l'ordre, voir pipeline.py) :
  1. shape_normalizer  - ramène n'importe quelle forme JSON à une liste plate
  2. field_mapper      - détecte les champs question/réponse/métadonnées
  3. classifier        - classe chaque entrée en famille (règle configurable,
                          fallback "generic_faq" garanti, jamais de perte)
  4. deduplicator       - contre le batch ET contre la base existante
  5. chunker            - découpage en chunks (convention identique au
                          pipeline d'ingestion notebooks/, dupliqué ici par
                          choix (voir tools/text_normalize.py : app/ et
                          notebooks/ ne s'importent jamais l'un l'autre)
  6. embedder            - embedding incrémental (n'encode que le nouveau)
  7. neo4j_loader         - MERGE (jamais DETACH DELETE)
  8. qdrant_indexer       - upsert (jamais de recréation de collection)
  9. verifier             - cohérence Neo4j<->Qdrant post-import

État des jobs et progression : job_store.py (Redis).
"""
