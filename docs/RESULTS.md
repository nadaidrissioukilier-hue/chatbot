# Résultats réels — entraide-mvp

Pipeline 00→06 exécuté intégralement dans ce dossier, données rechargées
fraîchement dans des conteneurs Neo4j/Qdrant/Redis dédiés à ce projet, LLM
réel (Qwen2.5-7B-Instruct-Q4_K_M via llama.cpp, pas de mock).

## Données (pipeline 00→06)

| Indicateur | Résultat | Cible guide |
|---|---|---|
| Services unifiés | 61 (100% avec conditions+documents) | ≥90% |
| Centres valides/uniques | 3 328 (90,3% géo valide avant dédup) | ≥3 500 |
| Programmes 2027 | 7 | — |
| FAQ AOS | 8/8 | — |
| Chunks | 10 257 | 8 000–15 000 |
| Relations Centre→Service | 21 044 | — |
| Moyenne relations/centre | 6,32 | ≤8 |
| EPS fallback | ~15% (mesuré sur pipeline source) | <20% |
| Cohérence Neo4j↔Qdrant | 100,0% (3 404/3 404 IDs) | 100% |

## Performance réelle (Qwen2.5-7B CPU, poste partagé)

| Requête | Retrieval | Génération LLM | Total |
|---|---|---|---|
| "أين أجد أقرب حضانة في سلا؟" (AR) | 9,4s | 101,9s | 111,3s |
| "Conditions pour la certification d'invalidité" (FR) | 33,9s | 47,8s | 81,8s |

**Honnête** : 80-110s par requête est lent — attendu sur un CPU partagé
avec un modèle 7B (le guide vise du 14B sur infra dédiée avec latence
cible <15-20s). Deux réponses ont été vérifiées manuellement : sources
correctes, contenu factuel présent dans le contexte, pas d'hallucination
visible. Un vrai déploiement voudrait soit une machine dédiée, soit un
modèle plus petit, soit une quantification plus agressive.

## Bug corrigé pendant la vérification

`app/src/inference/llamacpp_client.py` avait un timeout HTTP codé en dur
à 120s au lieu de lire `LLAMACPP_TIMEOUT` — une génération de 101,9s
passait de justesse, une autre a timeout à 120s. Corrigé pour lire la
config (`LLAMACPP_TIMEOUT=240` dans `.env`), reproductible sur toute
machine lente.
