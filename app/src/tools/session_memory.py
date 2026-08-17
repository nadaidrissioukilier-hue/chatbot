"""Mémoire conversationnelle par session (Redis), 2026-08-15.

Distincte du cache réponse (redis_cache.py, qui mémorise "question exacte
déjà répondue"): ceci mémorise "de quoi parle CETTE session" pour que le
retrieval d'une question de suivi elliptique (ex. "و ما هي الشروط والوثائق
المطلوبة" après une question sur "الترويض الحركي") reste sur le bon sujet
au lieu de repartir sur une recherche vectorielle générique.

TTL glissant (renouvelé à chaque tour) plutôt que fixe : une session active
ne doit pas expirer en plein échange, mais une session abandonnée doit
libérer la clé plutôt que de traîner indéfiniment.
"""
from typing import Any, Dict, List, Optional
import json

import redis

from src.config import REDIS_HOST, REDIS_PORT, REDIS_DB

SESSION_TTL_SECONDS = 1800  # 30 min glissant
MAX_TURNS = 4
ANSWER_EXCERPT_LEN = 220


class SessionMemory:
    def __init__(self):
        self.client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

    def _key(self, session_id: str) -> str:
        return f"en_session:{session_id}"

    def get_history(self, session_id: Optional[str]) -> List[Dict[str, Any]]:
        if not session_id:
            return []
        try:
            data = self.client.get(self._key(session_id))
            return json.loads(data) if data else []
        except Exception:
            return []

    def append_turn(
        self, session_id: Optional[str], query: str, intent: str,
        entities: Dict[str, Any], answer: str,
    ) -> None:
        if not session_id:
            return
        try:
            history = self.get_history(session_id)
            history.append({
                "query": query,
                "intent": intent,
                "entities": entities,
                "answer_excerpt": answer[:ANSWER_EXCERPT_LEN],
            })
            history = history[-MAX_TURNS:]
            self.client.setex(self._key(session_id), SESSION_TTL_SECONDS, json.dumps(history, ensure_ascii=False, default=str))
        except Exception:
            pass

    def close(self):
        self.client.close()
