/**
 * ENTRADE.MA — Dashboard admin, routage d'écrans + appels API.
 *
 * Squelette de structure (2026-08-17). Vanilla JS, pas de build step (même
 * choix que frontend/widget/widget.js). Consomme les endpoints définis
 * dans app/src/api/admin_import_routes.py (actuellement tous en 501 tant
 * que app/src/admin_import/ n'est pas implémenté) + POST /admin/login et
 * GET /admin/stats déjà existants dans app/src/api/main.py.
 *
 * Vues prévues (voir frontend/admin/views/) :
 *   - overview.js        : KPIs (fraîcheur données, totaux par type, cohérence)
 *   - import-upload.js   : upload du JSON
 *   - import-preview.js  : résultat dry-run (familles, doublons, mapping)
 *   - import-pipeline.js : suivi en direct des 9 étapes du pipeline
 *   - import-history.js  : journal des imports + rollback
 */
(function () {
  "use strict";

  var API_BASE = "http://localhost:8000";
  var root = document.getElementById("admin-root");

  // TODO : état d'auth (JWT en localStorage, comme le widget mémorise
  // langue/thème), routage entre vues, appels fetch() vers API_BASE.
  // Squelette de structure uniquement -- pas encore implémenté.

  function init() {
    root.textContent = "Dashboard admin — pas encore implémenté (squelette de structure).";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
