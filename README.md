# ENTRADE.MA — MVP localhost

Chatbot GraphRAG bilingue (arabe / français) pour l'Entraide Nationale du
Maroc. Pipeline **Router → Planner → Tool Executor (Qdrant + Neo4j + Redis)
→ Fusion/Ranking → Reranker → Generator (LLM) → Guardrail**, avec LLM local
réel (pas de mock) et widget de chat embarquable.

Tout tourne sur une seule machine (pas de split VM1/VM2, pas de
Nginx/TLS — inutile en local).

## Structure du projet

```
entraide-mvp/
├── app/                        # API FastAPI
│   ├── main.py                 # Point d'entrée : lance uvicorn sur src.api.main:app
│   ├── requirements.txt
│   ├── .env.example            # Modèle de config — copier en .env et renseigner
│   └── src/
│       ├── config.py           # Toute la config (lit .env) : ports, poids de ranking,
│       │                       # pénalités métier, timeouts, tailles de contexte...
│       ├── auth.py             # Auth API Key (widget) + JWT (admin)
│       ├── api/
│       │   └── main.py         # Endpoints FastAPI (/chat, /chat/stream, /health,
│       │                       # /admin/*, /metrics) — orchestre tout le pipeline
│       ├── routing/
│       │   └── intent_router.py    # Détecte l'intent (centre/service/faq/programme_2027/
│       │                           # about_institution/other) + langue + entités
│       │                           # (régions, institutions, populations cibles),
│       │                           # patterns bilingues AR/FR + Darija
│       ├── planning/
│       │   └── tool_planner.py     # Construit le plan d'outils selon l'intent
│       │                           # (quels outils appeler, dans quel ordre)
│       ├── tools/                  # Outils appelés par le planner
│       │   ├── vector_search.py    # Recherche hybride dense+sparse Qdrant (RRF natif)
│       │   ├── graph_search.py     # Expansion de graphe Neo4j (relations OFFRE/CIBLE/...)
│       │   ├── redis_cache.py      # Cache réponse (question déjà répondue)
│       │   ├── session_memory.py   # Mémoire courte par session (questions de suivi elliptiques)
│       │   ├── geo_resolver.py     # Résout ville/région texte libre -> région canonique Neo4j
│       │   ├── text_normalize.py   # Normalisation AR/FR (miroir de notebooks/etl_lib/ontology.py)
│       │   ├── sparse_vectorizer.py# Vectoriseur TF-IDF hashé (vecteur sparse)
│       │   └── calculator.py       # Calcul arithmétique direct, sans LLM
│       ├── ranking/
│       │   ├── fusion_ranker.py    # Formule métier : 0.35·RRF + 0.25·OFFRE + 0.25·population
│       │   │                       # + 0.15·géo, pénalités EPS/pop-manquante/pop-contradictoire
│       │   └── reranker.py         # Cross-encoder BGE-Reranker-v2-m3, pré-filtré par score
│       │                           # métier avant reranking (coût CPU)
│       ├── generation/
│       │   ├── context_builder.py  # Construit le prompt (contexte structuré + tronqué)
│       │   └── guardrail.py        # Vérifie la réponse : citations vs contexte réel,
│       │                           # chiffres non vérifiés, cohérence linguistique
│       ├── inference/
│       │   └── llamacpp_client.py  # Client HTTP vers le serveur llama.cpp local
│       └── retrieval/
│           └── pipeline.py         # Assemble routing->planning->tools->fusion->reranker
│
├── frontend/                   # Widget de chat embarquable
│   ├── widget/widget.js        # Composant Shadow DOM autonome (isolation CSS totale),
│   │                           # bouton flottant, choix langue AR/FR, thème clair/sombre,
│   │                           # streaming SSE, message de bienvenue localisé
│   ├── widget-test-page.html   # Page d'hôte pour tester l'intégration en un <script>
│   └── assets/                 # Images utilisées par la page de test
│
├── notebooks/                  # Pipeline d'ingestion ETL (Jupyter, exécutés programmatiquement)
│   ├── 00_Utils.ipynb          # Utilitaires partagés
│   ├── 01_Normalize.ipynb      # Normalisation des données brutes (AR/FR, régions, EPS...)
│   ├── 02_Chunk.ipynb          # Découpage en chunks pour l'indexation
│   ├── 03_Match.ipynb          # Matching centre<->service<->programme
│   ├── 04_Embed.ipynb          # Embeddings BGE-M3 (le plus long : ~60-90 min sur CPU)
│   ├── 05_Neo4j_Load.ipynb     # Charge le graphe (nœuds + relations)
│   ├── 06_Qdrant_Index.ipynb   # Indexe les vecteurs dense+sparse
│   ├── exec_notebook.py        # Exécute un notebook sans timeout artificiel (nbclient)
│   └── etl_lib/                # Ontologie sociale marocaine + utilitaires partagés
│       ├── ontology.py         # Population cibles, institutions (CEF/CFA/CRECHE/EPS...), régions
│       ├── io_utils.py
│       ├── sparse_vectorizer.py
│       └── faq_dataset.py
│
├── data/                       # Sorties du pipeline d'ingestion
│   ├── processed/              # Données normalisées par type (centres, services, FAQ, programmes)
│   ├── chunks/                 # Chunks prêts à l'embedding
│   ├── relations/               # Relations centre<->service<->programme<->population
│   ├── embeddings/             # Vecteurs BGE-M3 (⚠️ exclu du repo — 237 Mo, régénérable)
│   └── reports/                # Rapports de contrôle (couverture, taux de matching)
│
├── models/                     # ⚠️ Exclu du repo (voir "Récupérer le modèle" ci-dessous)
│   ├── Qwen2.5-7B-Instruct-Q4_K_M.gguf   # LLM principal (llama.cpp)
│   └── gemma/gemma-3-4b-it-Q4_K_M.gguf   # Modèle alternatif pour comparaison
│
├── infra/
│   └── docker-compose.yml      # Neo4j + Qdrant + Redis (conteneurs entraide-mvp-*)
│
├── scripts/
│   ├── start_all.sh / stop_all.sh   # Démarre/arrête stockage + llama.cpp + API
│   ├── start_llama.sh / start_gemma_test.sh
│   ├── healthcheck.sh
│   ├── backup_daily.sh
│   ├── init_qdrant.py
│   ├── embed_incremental.py         # Ré-embed seulement les nouveaux chunks
│   ├── normalize_faq_dataset.py     # Ingestion d'un jeu de FAQ additionnel
│   ├── verify_graph_qdrant_sync.py  # Vérifie la cohérence des IDs Neo4j<->Qdrant
│   ├── eval_retrieval.py            # Évaluation routing/retrieval (20 requêtes types)
│   ├── eval_faithfulness.py         # Évaluation fidélité réponse LLM vs contexte
│   ├── test_guardrail.py            # Test du guardrail (citations hors-contexte)
│   ├── test_e2e.py                  # Bout en bout (8 questions du guide)
│   └── diag_ranking.py              # Diagnostic détaillé du scoring de ranking
│
├── docs/
│   ├── RESULTS.md               # Indicateurs pipeline vs cibles du guide
│   ├── eval_*_results.json      # Résultats des évaluations
│   ├── screenshots/             # Captures du widget en action
│   └── soutenance/              # Rapport de soutenance (LaTeX + PDF)
│
└── .gitignore                  # Exclut models/, data/embeddings/, .env, logs/, backups/, .venv/
```

## Architecture du pipeline de requête

```
Question utilisateur
   │
   ▼
IntentRouter        → intent (centre_search/service_search/faq_search/
   │                    programme_2027/about_institution/other) + langue + entités
   ▼
ToolPlanner         → quels outils appeler (vector_search, graph_expansion, cache_check)
   │
   ▼
Tool Executor       → Qdrant (hybride dense+sparse) + Neo4j (expansion graphe) + Redis (cache)
   │
   ▼
FusionRanker        → combine les scores selon la formule métier + pénalités
   │
   ▼
Reranker            → cross-encoder BGE-Reranker-v2-m3 (affine l'ordre final)
   │
   ▼
ContextBuilder       → construit le prompt (contexte structuré, tronqué)
   │
   ▼
LLM (llama.cpp)      → génère la réponse
   │
   ▼
Guardrail            → vérifie citations/chiffres vs contexte, langue, format
   │
   ▼
Réponse (JSON ou SSE streaming)
```

Cas particuliers court-circuités (pas de LLM, réponse quasi-instantanée) :
salutations (`other`) et questions sur l'institution elle-même
(`about_institution`, ex. "c'est quoi l'Entraide Nationale ?") — réponses
factuelles fixes plutôt que de lancer une recherche vouée à échouer.

## Démarrer

```bash
cd entraide-mvp
cp app/.env.example app/.env   # puis renseigner les vraies valeurs (mots de passe, clés)
scripts/start_all.sh           # stockage (Docker) + llama.cpp + API, dans cet ordre
```

Puis :
```bash
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: $(grep API_KEY_WIDGET app/.env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"query": "أين أجد أقرب حضانة في سلا؟"}'
```

Widget de test : servir `frontend/` (`python3 -m http.server 8090`) puis
ouvrir `http://localhost:8090/widget-test-page.html`.

Arrêter : `scripts/stop_all.sh` (garde le stockage actif ; `docker compose
-f infra/docker-compose.yml down` pour tout arrêter).

## Récupérer le modèle (exclu du repo, ~4.7 Go)

```bash
mkdir -p models
curl -L -o models/Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf
```

## Reconstruire les données depuis zéro

```bash
source .venv/bin/activate
cd notebooks
for nb in 00_Utils 01_Normalize 02_Chunk 03_Match 04_Embed 05_Neo4j_Load 06_Qdrant_Index; do
    python3 exec_notebook.py "$nb.ipynb"
done
```

`04_Embed` est le plus long (BGE-M3 sur CPU, ~60-90 min pour ~10 000
chunks — voir `data/embeddings/embed_progress.log` pour suivre la
progression réelle plutôt que de juger sur les premières secondes,
biaisées par le "warmup" du modèle).

## Évaluer

```bash
source .venv/bin/activate
python3 scripts/eval_retrieval.py      # routing + retrieval, sans LLM (rapide)
python3 scripts/eval_faithfulness.py   # bout en bout avec LLM (lent, ~1-2 min/requête sur CPU)
python3 scripts/test_guardrail.py      # vérifie que le guardrail rejette les hallucinations
python3 scripts/diag_ranking.py        # décompose le score de ranking pour une requête donnée
```
