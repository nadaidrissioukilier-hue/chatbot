#!/usr/bin/env python3
"""Point d'entrée de l'API GraphRAG ENTRADE.MA (VM2)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    import uvicorn
    from src.config import API_HOST, API_PORT, LOG_LEVEL

    uvicorn.run("src.api.main:app", host=API_HOST, port=API_PORT, log_level=LOG_LEVEL.lower())
