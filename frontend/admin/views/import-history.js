/**
 * Vue "Historique" du dashboard admin — squelette de structure
 * (2026-08-17).
 *
 * Liste des imports passés (GET /admin/import/history) : fichier, date,
 * famille de résultats, statut, bouton "Annuler" -> POST
 * /admin/import/{id}/rollback (supprime uniquement les entity_id créés par
 * ce job précis, jamais un wipe global -- voir
 * app/src/admin_import/pipeline.py::run_rollback).
 *
 * Pas encore implémenté.
 */
