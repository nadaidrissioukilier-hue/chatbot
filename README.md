# ENTRADE.MA — MVP localhost

Version condensée du guide `ENTRADE_MA_Guide_Deploiement_GraphRAG.pdf` :
même principe (Router → Planner → Qdrant+Neo4j+Redis → Fusion → Reranker →
Generator → Guardrail), même ontologie métier, mais **tout tourne sur ce
PC** — pas de split VM1/VM2, pas de Nginx/TLS (pas nécessaire en local).

## Différences avec `entraide-vm2/`

| | entraide-vm2 | entraide-mvp |
|---|---|---|
| Topologie | VM1 (inference) / VM2 (stockage+API) séparées | Tout en local |
| LLM | Mock (`mock_llamacpp.py`) pour les tests | **Vrai** Qwen2.5-7B-Instruct via llama.cpp |
| Données | Anciennes (copiées avant la correction des notebooks) | Pipeline corrigé (00→06) exécuté ici, dans ce dossier |
| Nginx/TLS | Oui (prod) | Non (inutile en localhost) |

## Structure

```
entraide-mvp/
├── notebooks/       # Pipeline d'ingestion 00_Utils -> 06_Qdrant_Index
│   └── etl_lib/      # Ontologie + utilitaires partagés
├── data/            # Sorties du pipeline (processed/chunks/relations/embeddings)
├── app/             # API FastAPI (identique à entraide-vm2/app, testée)
├── models/          # Qwen2.5-7B-Instruct-Q4_K_M.gguf
├── infra/           # docker-compose.yml (Neo4j/Qdrant/Redis)
├── scripts/         # start_all.sh, stop_all.sh, start_llama.sh, tests
└── logs/
```

## Démarrer

```bash
cd entraide-mvp
scripts/start_all.sh   # stockage + llama.cpp + API, dans cet ordre
```

Puis :
```bash
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: $(grep API_KEY_WIDGET app/.env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"query": "أين أجد أقرب حضانة في سلا؟"}'
```

Arrêter : `scripts/stop_all.sh` (garde le stockage actif ; `docker compose
-f infra/docker-compose.yml down` pour tout arrêter).

## Reconstruire les données depuis zéro

```bash
source .venv/bin/activate
cd notebooks
for nb in 00_Utils 01_Normalize 02_Chunk 03_Match 04_Embed 05_Neo4j_Load 06_Qdrant_Index; do
    python3 exec_notebook.py "$nb.ipynb"
done
```

`04_Embed` est le plus long (BGE-M3 sur CPU, ~60-90 min pour 10 257
chunks sur une machine partagée — voir `notebooks/etl_lib/` et le log
`data/embeddings/embed_progress.log` pour suivre la progression réelle).
