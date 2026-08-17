/**
 * Vue "Preview" (dry-run) du dashboard admin — squelette de structure
 * (2026-08-17).
 *
 * Affiche le PreviewResult (voir app/src/admin_import/models.py) :
 *   - mapping de champs proposé (question/réponse/catégorie), éditable si
 *     confidence < IMPORT_FIELD_MAPPING_MIN_CONFIDENCE (config.py)
 *   - compteurs par famille (family_counts), doublons détectés
 *   - warnings (ex. forme JSON inhabituelle, unclassified_count > 0 --
 *     ne devrait jamais arriver grâce au fallback generic_faq)
 *
 * Aucune écriture Neo4j/Qdrant à ce stade -- seul le bouton "Confirmer
 * l'import" déclenche POST /admin/import/{id}/commit.
 *
 * Pas encore implémenté.
 */
