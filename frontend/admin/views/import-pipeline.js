/**
 * Vue "Pipeline en direct" du dashboard admin — squelette de structure
 * (2026-08-17).
 *
 * Affiche les 9 étapes (voir app/src/admin_import/models.py::ImportStage)
 * comme un flux horizontal, statut + compteurs par étape, via polling
 * régulier de GET /admin/import/{id}/status (même logique que le widget de
 * chat qui poll GET /health, voir frontend/widget/widget.js::checkHealth).
 *
 * Attention affichage : l'étape "embedded" peut sembler bloquée plusieurs
 * dizaines de secondes au démarrage (effet de "warmup" BGE-M3 déjà observé
 * sur le pipeline d'ingestion initial, voir docs/RESULTS.md) -- ne pas
 * laisser croire à une erreur avant un délai raisonnable.
 *
 * Pas encore implémenté.
 */
