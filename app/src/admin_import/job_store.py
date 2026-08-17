"""État persistant des jobs d'import, dans Redis -- même client que
tools/redis_cache.py et tools/session_memory.py, préfixe de clé dédié
("import_job:{job_id}") pour ne pas entrer en collision avec le cache de
réponses ou la mémoire de session.

Consommé par :
  - admin_import_routes.py::GET /admin/import/{id}/status (polling)
  - frontend/admin/views/import-pipeline.js (vue pipeline en direct)

TTL des jobs : voir config.py IMPORT_JOB_TTL (les jobs commités passent
aussi dans un historique durable, pas seulement Redis -- voir
GET /admin/import/history, à préciser lors de l'implémentation).

Squelette uniquement -- logique pas encore implémentée."""
from typing import Optional

from .models import ImportJob, ImportStage


def create_job(filename: str, uploaded_by: str) -> ImportJob:
    raise NotImplementedError


def update_stage(job_id: str, stage: ImportStage, counts: Optional[dict] = None) -> None:
    """Appelé par pipeline.py après chaque étape -- c'est ce qui alimente
    la vue pipeline en direct côté dashboard."""
    raise NotImplementedError


def get_job(job_id: str) -> Optional[ImportJob]:
    raise NotImplementedError


def list_jobs(limit: int = 50) -> list:
    """Pour GET /admin/import/history."""
    raise NotImplementedError
