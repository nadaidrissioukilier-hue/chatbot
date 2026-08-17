/**
 * Vue "Overview" du dashboard admin — squelette de structure (2026-08-17).
 *
 * Doit afficher les KPIs du plan produit (catégories B/D/E) :
 *   - total par type d'entité (Centre/Service/FAQ/Programme/Institution)
 *   - fraîcheur (date du dernier import réussi, GET /admin/import/history)
 *   - cohérence Neo4j<->Qdrant (réutilise GET /admin/stats existant, à
 *     étendre côté API pour exposer ce chiffre)
 *   - nombre d'imports par période, délai moyen upload->commit
 *
 * Pas encore implémenté.
 */
