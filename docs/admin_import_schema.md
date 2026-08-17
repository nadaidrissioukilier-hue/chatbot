# Mode admin d'import — schéma attendu et conventions

Squelette de documentation (2026-08-17), en parallèle du squelette de code
dans `app/src/admin_import/` et `frontend/admin/`. Décrit l'intention ; à
tenir à jour au fur et à mesure de l'implémentation réelle.

## Formes de JSON acceptées (voir `shape_normalizer.py`)

| Forme | Exemple | Détection |
|---|---|---|
| Tableau plat | `[{...}, {...}]` | racine est une liste |
| Objet conteneur | `{"faqs": [...]}` | 1ère liste d'objets trouvée dans l'arbre |
| Dict-de-dicts | `{"id1": {...}, "id2": {...}}` | racine est un objet dont toutes les valeurs sont des objets |
| JSONL | une entrée JSON par ligne | extension `.jsonl` ou échec du parse JSON global |

## Détection des champs question/réponse (voir `field_mapper.py`)

Synonymes reconnus par l'heuristique (niveau 1) :

- **Question** : `question`, `q`, `query`, `intitulé`, `سؤال`, `question_ar`, `question_fr`
- **Réponse** : `answer`, `a`, `reponse`, `réponse`, `response`, `جواب`, `إجابة`

Si aucun champ ne matche avec une confiance suffisante
(`config.py::IMPORT_FIELD_MAPPING_MIN_CONFIDENCE`), le LLM local propose un
mapping (niveau 2) — toujours soumis à confirmation admin dans l'écran
`import-preview` avant `/commit`.

## Familles de classification (voir `classification_rules.json`)

Config versionnée, pas de code à modifier pour ajouter une famille. Trois
règles par défaut (reprises du dataset `data_faq`, 129 entrées, déjà
validé) :

1. **`service`** — présence de conditions + documents requis → traité comme
   un Service existant
2. **`institution_profile`** — présence d'acronyme + nom complet → enrichit
   un nœud Institution (existant ou nouveau)
3. **`generic_faq`** — repli garanti, aucune entrée n'est jamais rejetée

## Garanties non négociables

- **Zéro perte** : `unclassified_count` doit toujours être 0 dans
  `PreviewResult` (fallback `generic_faq` systématique)
- **Zéro wipe** : `neo4j_loader.py` n'utilise que `MERGE`,
  `qdrant_indexer.py` n'utilise que `upsert` — jamais de suppression des
  données existantes lors d'un import admin
- **Traçabilité** : chaque job garde la liste des `entity_id` créés/modifiés
  pour permettre un rollback ciblé

## KPIs de suivi

Voir la discussion produit du 2026-08-17 pour la liste complète (catégories
A à F : pipeline, qualité des données, impact chatbot, système,
opérationnel, sécurité). Le dashboard (`frontend/admin/views/overview.js`)
doit à terme les exposer tous, pas seulement en logs serveur.
