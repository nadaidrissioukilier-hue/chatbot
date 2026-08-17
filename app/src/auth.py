"""Authentification: clé API pour le widget public, JWT pour le portail admin.

Nouveau module (absent de la v1) — comble le gap explicitement noté par
l'ancienne équipe: "Admin endpoints -> Pas d'auth (à ajouter en prod)".
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.config import (
    API_KEY_WIDGET, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES,
    ADMIN_USERNAME, ADMIN_PASSWORD_HASH,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


def require_widget_key(api_key: Optional[str] = Depends(_api_key_header)) -> str:
    """Protège /chat, /chat/stream, /health (usage widget public)."""
    if not api_key or api_key != API_KEY_WIDGET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clé API widget invalide ou absente")
    return api_key


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_admin_credentials(username: str, password: str) -> bool:
    if username != ADMIN_USERNAME or not ADMIN_PASSWORD_HASH:
        return False
    return pwd_context.verify(password, ADMIN_PASSWORD_HASH)


def require_admin(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> str:
    """Protège /admin/*, /ingest/* (portail admin, JWT Bearer)."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token JWT requis")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise JWTError("sub manquant")
        return username
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token JWT invalide ou expiré")
