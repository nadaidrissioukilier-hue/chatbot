"""Configuration centralisée — source de vérité unique (voir .env.example)."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
CHUNKS_DIR = DATA_DIR / "chunks"
PROCESSED_DIR = DATA_DIR / "processed"

# === Neo4j ===
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme-neo4j")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# === Qdrant — une seule collection, vecteurs nommés dense+sparse ===
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "entraide_ma")
QDRANT_DENSE_VECTOR_NAME = os.getenv("QDRANT_DENSE_VECTOR_NAME", "dense")
QDRANT_SPARSE_VECTOR_NAME = os.getenv("QDRANT_SPARSE_VECTOR_NAME", "sparse")

# === Redis ===
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
CACHE_TTL = int(os.getenv("CACHE_TTL", 3600))

# === Llama.cpp (VM1) - Pure HTTP, pas de package openai ===
LLAMACPP_URL = os.getenv("LLAMACPP_URL", "http://localhost:8080")
LLAMACPP_MODEL = os.getenv("LLAMACPP_MODEL", "qwen2.5-14b-instruct-q4_k_m")
LLAMACPP_TIMEOUT = int(os.getenv("LLAMACPP_TIMEOUT", 120))

# === FastAPI ===
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))

# === Embeddings — DOIT matcher le modèle utilisé à l'indexation ===
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", 1024))

# === Reranker ===
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_BATCH_SIZE = int(os.getenv("RERANKER_BATCH_SIZE", 32))
# Mesuré en diagnostic (scripts/time_retrieval.py) : ~0.5s/candidat CPU pour
# le cross-encoder BGE-v2-m3 -> 35.6s pour 68 candidats fusionnés, alors que
# seuls TOP_K_RERANK=10 (puis 4 côté context_builder) sont utilisés au final.
# On ne fait scorer par le cross-encoder que les meilleurs candidats selon le
# score métier (fusion, désormais rééquilibré service/centre) plutôt que la
# totalité -> ~3x plus rapide sans perte de qualité mesurable, tant que le
# bon résultat reste dans ce pool (vérifié : il l'est, voir diag_ranking.py).
RERANKER_PRE_FILTER_POOL = int(os.getenv("RERANKER_PRE_FILTER_POOL", 20))

# === Richesse du contexte / des réponses (2026-08-13, "donner le max de
# text data") === Ces valeurs pilotent combien du contenu déjà récupéré et
# reranké (TOP_K_RERANK ci-dessus) est effectivement transmis au LLM et
# cité en sources -- avant, seuls 4 résultats et des extraits courts
# (300/180 caractères) étaient utilisés, alors que jusqu'à 10 résultats
# reranké étaient déjà disponibles sans coût de calcul supplémentaire.
# Compromis assumé : plus de contexte = prompt plus long = génération plus
# lente sur ce CPU (déjà 60-160s/requête) -- ajustable via env si besoin.
CONTEXT_TOP_N_PROMPT = int(os.getenv("CONTEXT_TOP_N_PROMPT", 6))
CONTEXT_TEXT_TRUNCATE = int(os.getenv("CONTEXT_TEXT_TRUNCATE", 700))
CONTEXT_FIELD_TRUNCATE = int(os.getenv("CONTEXT_FIELD_TRUNCATE", 350))
GROUNDED_MAX_TOKENS = int(os.getenv("GROUNDED_MAX_TOKENS", 900))
GENERAL_KNOWLEDGE_MAX_TOKENS = int(os.getenv("GENERAL_KNOWLEDGE_MAX_TOKENS", 600))

# === Retrieval Params ===
TOP_K_DENSE = int(os.getenv("TOP_K_DENSE", 50))
TOP_K_SPARSE = int(os.getenv("TOP_K_SPARSE", 50))
TOP_K_GRAPH = int(os.getenv("TOP_K_GRAPH", 20))
TOP_K_RERANK = int(os.getenv("TOP_K_RERANK", 10))
RRF_K = int(os.getenv("RRF_K", 60))

# === Fusion Weights (métier) — doit sommer à 1.0 ===
# RRF baissé (0.45->0.35) et population monté (0.15->0.25) suite au diagnostic
# scripts/diag_ranking.py sur "خدمات لذوي الإعاقة" : le rang vectoriel brut est
# bruité sur des requêtes arabes courtes (un Centre "Femmes en sit. diff."
# atteignait rrf=1.000 et dominait un Service "شهادة الإعاقة" au pop_score
# pourtant correct) ; le signal population (déterministe, tiré du payload) est
# plus fiable pour la véracité que le rang brut du vecteur.
WEIGHT_RRF = float(os.getenv("WEIGHT_RRF", 0.35))
WEIGHT_OFFRE = float(os.getenv("WEIGHT_OFFRE", 0.25))
WEIGHT_POPULATION = float(os.getenv("WEIGHT_POPULATION", 0.25))
WEIGHT_GEO = float(os.getenv("WEIGHT_GEO", 0.15))

# === Pénalités métier ===
PENALTY_EPS = float(os.getenv("PENALTY_EPS", 0.70))
PENALTY_NO_POP = float(os.getenv("PENALTY_NO_POP", 0.85))
# Contradiction explicite (population renseignée mais différente de celle
# demandée) est un signal plus fort que "pas d'info population" -> pénalité
# plus sévère. Avant ce fix, une population manquante ET une population
# fausse recevaient exactement la même pénalité (0.85), donc un résultat
# activement hors-cible n'était pas distingué d'un résultat neutre.
PENALTY_POP_MISMATCH = float(os.getenv("PENALTY_POP_MISMATCH", 0.55))

# Boost "question quasi-identique" (chunk_type=faq_question, cf.
# ingestion data_faq du 2026-08-12) : multiplicatif comme les pénalités
# ci-dessus (pas un 5e poids additif, casserait la somme=1.0 des WEIGHT_*).
# Rang plutôt que score brut : le score RRF Qdrant n'est pas comparable
# entre chunk_type sans recalibrage, mais son RANG parmi les résultats
# vectoriels bruts reste un signal fiable de "quasi-doublon de question".
BOOST_FAQ_QUESTION_MATCH = float(os.getenv("BOOST_FAQ_QUESTION_MATCH", 1.20))
FAQ_QUESTION_MATCH_RANK_THRESHOLD = int(os.getenv("FAQ_QUESTION_MATCH_RANK_THRESHOLD", 3))

# === Intent Detection ===
INTENT_TYPES = ["centre_search", "service_search", "faq_search", "programme_2027", "other"]

# === Sécurité / Auth ===
API_KEY_WIDGET = os.getenv("API_KEY_WIDGET", "changeme-widget-api-key")
JWT_SECRET = os.getenv("JWT_SECRET", "changeme-generate-with-openssl-rand-hex-32")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", 60))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

# === Monitoring ===
ENABLE_METRICS = os.getenv("ENABLE_METRICS", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# === Ontologie métier (identique aux scripts d'ingestion — ne pas diverger) ===
INSTITUTION_MAP = {
    "CEF": {"ar": "مراكز التربية والتكوين", "fr": "Centre d'Éducation et de Formation", "polyvalence": 2},
    "CFA": {"ar": "مراكز التكوين بالتدرج المهني", "fr": "Centre de Formation par Apprentissage", "polyvalence": 1},
    "CAPE": {"ar": "مراكز المواكبة لحماية الطفولة", "fr": "Centre d'Accompagnement pour la Protection de l'Enfance", "polyvalence": 1},
    "UPE": {"ar": "وحدات حماية الطفولة", "fr": "Unité de Protection de l'Enfance", "polyvalence": 1},
    "EPS": {"ar": "مؤسسات الرعاية الاجتماعية", "fr": "Établissement de Protection Sociale", "polyvalence": 5},
    "CJPA": {"ar": "المراكز الاجتماعية للخدمات النهارية للأشخاص المسنين", "fr": "Centre de Jour pour Personnes Âgées", "polyvalence": 2},
    "COAPH": {"ar": "مراكز توجيه ومساعدة الأشخاص في وضعية إعاقة", "fr": "Centre d'Orientation et d'Aide aux Personnes Handicapées", "polyvalence": 2},
    "CPSH": {"ar": "مراكز تأهيل وإدماج الأشخاص في وضعية إعاقة", "fr": "Centre de Promotion Sociale des Handicapés", "polyvalence": 2},
    "CRECHE": {"ar": "حضانة", "fr": "Crèche", "polyvalence": 1},
    "JE": {"ar": "روض الأطفال", "fr": "Jardin d'Enfants", "polyvalence": 1},
    "CAREPS": {"ar": "مراكز الرعاية والتأهيل", "fr": "Centre de Rééducation et Réadaptation", "polyvalence": 3},
    # Découverts en analysant ~/Downloads/data_faq (2026-08-12) -- garder en
    # phase avec notebooks/etl_lib/ontology.py (source dupliquée, voir note ci-dessus).
    "CAS": {"ar": "مراكز المساعدة الاجتماعية", "fr": "Centre d'Assistance Sociale", "polyvalence": 5},
    "EMF": {"ar": "الفضاءات متعددة الوظائف للنساء", "fr": "Espace Multifonctionnel Femmes", "polyvalence": 1},
    "SAMU_SOCIAL": {"ar": "مؤسسات الإسعاف الاجتماعي المتنقل", "fr": "SAMU Social", "polyvalence": 1},
}
EPS_CODE = "EPS"

POPULATION_CIBLES = {
    "enfants": {"ar": "الأطفال", "fr": "Enfants", "priorite": 1},
    "femmes": {"ar": "النساء", "fr": "Femmes", "priorite": 2},
    "personnes_agees": {"ar": "المسنين", "fr": "Personnes Âgées", "priorite": 3},
    "personnes_handicapees": {"ar": "الأشخاص ذوو الإعاقة", "fr": "Personnes Handicapées", "priorite": 4},
    "jeunes": {"ar": "الشباب", "fr": "Jeunes", "priorite": 5},
    "famille": {"ar": "الأسرة", "fr": "Famille", "priorite": 6},
}
