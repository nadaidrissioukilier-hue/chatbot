/**
 * Vue "Upload" du dashboard admin — squelette de structure (2026-08-17).
 *
 * Formulaire de dépôt d'un fichier .json/.jsonl -> POST /admin/import
 * (voir app/src/api/admin_import_routes.py). Limite de taille cliente
 * alignée sur config.py::IMPORT_MAX_FILE_SIZE_MB. Redirige vers
 * import-preview.js une fois le job créé (statut "uploaded").
 *
 * Pas encore implémenté.
 */
