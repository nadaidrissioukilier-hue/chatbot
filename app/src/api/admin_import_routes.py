"""Endpoints du mode admin d'import (voir app/src/admin_import/).

Séparé de api/main.py (déjà volumineux) plutôt qu'ajouté aux routes
/admin/* existantes -- même style que les autres modules du projet, un
fichier par responsabilité. Auth identique aux autres routes /admin/* :
require_admin (JWT), voir src/auth.py.

Squelette uniquement -- chaque handler retourne 501 Not Implemented tant
que app/src/admin_import/pipeline.py n'est pas implémenté. Prêt à être
branché dans api/main.py via :

    from src.api.admin_import_routes import router as admin_import_router
    app.include_router(admin_import_router)
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from src.auth import require_admin
from src.admin_import.models import ImportCommitRequest

router = APIRouter(prefix="/admin/import", tags=["admin-import"])

_NOT_IMPLEMENTED = "Pipeline d'import pas encore implémenté (squelette de structure, voir app/src/admin_import/)."


@router.post("", dependencies=[Depends(require_admin)])
async def upload_faq_json(file: UploadFile = File(...)):
    """Upload d'un JSON Q/R -> crée un job et lance la phase preview
    (étapes 1-4, aucune écriture Neo4j/Qdrant)."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/{job_id}/status", dependencies=[Depends(require_admin)])
async def get_import_status(job_id: str):
    """Polling pour la vue pipeline en direct (frontend/admin/views/import-pipeline.js)."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/{job_id}/preview", dependencies=[Depends(require_admin)])
async def get_import_preview(job_id: str):
    """Résultat du dry-run : familles détectées, doublons, mapping proposé."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/{job_id}/commit", dependencies=[Depends(require_admin)])
async def commit_import(job_id: str, body: ImportCommitRequest):
    """Écriture réelle (étapes 5-9). Sauvegarde auto à déclencher avant
    (voir scripts/backup_daily.sh) une fois implémenté."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.post("/{job_id}/rollback", dependencies=[Depends(require_admin)])
async def rollback_import(job_id: str):
    """Supprime uniquement les entity_id créés par ce job (jamais un wipe global)."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)


@router.get("/history", dependencies=[Depends(require_admin)])
async def get_import_history(limit: int = 50):
    """Journal des imports passés (traçabilité/audit)."""
    raise HTTPException(status_code=501, detail=_NOT_IMPLEMENTED)
