"""Cache Redis distribué"""
from typing import Optional, Dict, Any
import redis
import json
from src.config import REDIS_HOST, REDIS_PORT, REDIS_DB, CACHE_TTL

class RedisCache:
    def __init__(self):
        self.client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True
        )
        self.ttl = CACHE_TTL
    
    def get(self, query: str, query_type: str = "") -> Optional[Any]:
        """Récupère du cache"""
        key = self._make_key(query, query_type)
        
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
        except Exception:
            pass
        
        return None
    
    def set(self, query: str, value: Any, query_type: str = "", ttl: int = None) -> None:
        """Stocke en cache avec TTL"""
        key = self._make_key(query, query_type)
        ttl = ttl or self.ttl
        
        try:
            self.client.setex(
                key,
                ttl,
                json.dumps(value, default=str)
            )
        except Exception:
            pass
    
    def delete(self, query: str, query_type: str = "") -> None:
        """Supprime du cache"""
        key = self._make_key(query, query_type)
        self.client.delete(key)
    
    def clear_pattern(self, pattern: str = "*") -> int:
        """Supprime les clés matching un pattern"""
        keys = self.client.keys(pattern)
        if keys:
            return self.client.delete(*keys)
        return 0
    
    def _make_key(self, query: str, query_type: str) -> str:
        """Crée une clé unique"""
        import hashlib
        query_hash = hashlib.md5(query.encode()).hexdigest()
        prefix = f"en_cache_{query_type}" if query_type else "en_cache"
        return f"{prefix}:{query_hash}"
    
    def get_stats(self) -> Dict[str, Any]:
        """Récupère les stats du cache"""
        info = self.client.info()
        return {
            "used_memory": info.get("used_memory_human"),
            "connected_clients": info.get("connected_clients"),
            "expired_keys": info.get("expired_keys"),
            "evicted_keys": info.get("evicted_keys")
        }
    
    def close(self):
        self.client.close()
