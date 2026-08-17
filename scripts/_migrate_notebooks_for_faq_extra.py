#!/usr/bin/env python3
"""Migration ponctuelle des notebooks 02/05/06 pour integrer les sorties de
normalize_faq_dataset.py (faq_extra_service/general.jsonl, institution_enrich.jsonl)
dans le pipeline durable, pour qu'un futur "Reconstruire les donnees depuis
zero" (voir README.md) les inclue automatiquement -- 06_Qdrant_Index recree
sa collection a chaque execution, 05_Neo4j_Load vide toute la base a chaque
execution : sans cette migration, les nouvelles FAQ seraient silencieusement
perdues au prochain rebuild complet.

Idempotent : chaque insertion porte un marqueur unique, verifie avant d'agir.
Les modifications de cellules existantes se font par remplacement de
sous-chaine EXACTE (jamais de retype a la main d'une cellule entiere) pour
ne jamais perdre de code par erreur de recopie.
"""
import nbformat

MARKER = "# === FAQ_EXTRA_INGESTION_BLOCK ==="
NB_DIR = "/home/ubunto/entraide-mvp/notebooks"


def already_migrated(nb) -> bool:
    return any(MARKER in "".join(c.get("source", "")) for c in nb.cells)


def insert_after(nb, anchor_substring: str, new_source: str):
    for i, cell in enumerate(nb.cells):
        if cell.cell_type == "code" and anchor_substring in "".join(cell.source):
            nb.cells.insert(i + 1, nbformat.v4.new_code_cell(new_source))
            return
    raise RuntimeError(f"Cellule ancre introuvable: {anchor_substring!r}")


def patch_cell(nb, old_substring: str, new_substring: str):
    """Remplace old_substring par new_substring DANS le source d'une cellule
    existante, en preservant tout le reste tel quel. Echoue si old_substring
    n'apparait pas exactement une fois (garde-fou anti-corruption)."""
    matches = [c for c in nb.cells if c.cell_type == "code" and "".join(c.source).count(old_substring) == 1]
    if len(matches) != 1:
        raise RuntimeError(f"Anchor trouve dans {len(matches)} cellule(s) (attendu 1): {old_substring!r}")
    cell = matches[0]
    src = "".join(cell.source) if isinstance(cell.source, list) else cell.source
    cell.source = src.replace(old_substring, new_substring)


# ============================== 02_Chunk ==============================
def migrate_02_chunk():
    path = f"{NB_DIR}/02_Chunk.ipynb"
    nb = nbformat.read(path, as_version=4)
    if already_migrated(nb):
        print("02_Chunk: deja migre, rien a faire")
        return

    insert_after(nb, 'faq_chunks = []', f'''{MARKER}
# Chunks pour les 121 enregistrements issus de data_faq (voir
# scripts/normalize_faq_dataset.py) : familles A (service) + C (generique)
# -> 2 chunks chacune (question seule / question+reponse, pour permettre le
# matching question-a-question ET question-a-contenu, cf. discussion metier
# du 2026-08-12) ; famille B (fiches Institution) -> 1 chunk profil, rattache
# a l'entite Institution existante (entity_id = code, ex "CEF").
faq_extra_service = load_jsonl(PROCESSED_DIR / "faq_extra_service.jsonl")
faq_extra_general = load_jsonl(PROCESSED_DIR / "faq_extra_general.jsonl")
institution_enrich = load_jsonl(PROCESSED_DIR / "institution_enrich.jsonl")

faq_extra_chunks = []
for f in faq_extra_service + faq_extra_general:
    meta = {{
        "population_cible": " | ".join(f.get("population_cible", [])),
        "institutions": f.get("institutions", []),
        "section": f.get("category", ""),
    }}
    q = make_chunk("FAQ", f["id"], "faq_question", f["question_ar"], **meta)
    c = make_chunk("FAQ", f["id"], "faq_content", f"{{f['question_ar']}} {{f['reponse_ar']}}", **meta)
    faq_extra_chunks.extend(x for x in (q, c) if x)

institution_profile_chunks = []
for ip in institution_enrich:
    meta = {{"population_cible": " | ".join(ip.get("population_cible", [])), "institutions": [ip["institution_code"]]}}
    c = make_chunk("Institution", ip["institution_code"], "institution_profile",
                    f"{{ip['question_ar']}} {{ip['reponse_ar']}}", **meta)
    if c:
        institution_profile_chunks.append(c)

print(f"Chunks FAQ (data_faq)        : {{len(faq_extra_chunks)}} ({{len(faq_extra_service) + len(faq_extra_general)}} entrees x2)")
print(f"Chunks Institution (profils) : {{len(institution_profile_chunks)}} ({{len(institution_enrich)}} codes)")
''')

    patch_cell(
        nb,
        "all_chunks = service_chunks + centre_chunks + programme_chunks + faq_chunks",
        f"{MARKER}\n"
        "all_chunks = (\n"
        "    service_chunks + centre_chunks + programme_chunks + faq_chunks\n"
        "    + faq_extra_chunks + institution_profile_chunks\n"
        ")",
    )

    nbformat.write(nb, path)
    print("02_Chunk: migre")


# ============================== 05_Neo4j_Load ==============================
def migrate_05_neo4j():
    path = f"{NB_DIR}/05_Neo4j_Load.ipynb"
    nb = nbformat.read(path, as_version=4)
    if already_migrated(nb):
        print("05_Neo4j_Load: deja migre, rien a faire")
        return

    insert_after(nb, 'services = load_jsonl(PROCESSED_DIR / "services_unified.jsonl")', f'''{MARKER}
faq_extra_service = load_jsonl(PROCESSED_DIR / "faq_extra_service.jsonl")
faq_extra_general = load_jsonl(PROCESSED_DIR / "faq_extra_general.jsonl")
institution_enrich = load_jsonl(PROCESSED_DIR / "institution_enrich.jsonl")
print(f"data_faq: {{len(faq_extra_service)}} FAQ service, {{len(faq_extra_general)}} FAQ generiques, "
      f"{{len(institution_enrich)}} profils Institution")
''')

    insert_after(nb, 'print(f"{len(services)} Service, {len(INSTITUTION_MAP)} Institution', f'''{MARKER}
# FAQ issues de data_faq (familles A+C) -- memes proprietes que les FAQ AOS
# d'origine + category/family pour tracabilite. Lien par SIGNAUX CONFIANTS
# uniquement (population/institution extraits par regex/keyword, cf
# etl_lib.ontology) -- pas de lien FAQ->Service invente : un matching
# semantique fiable question<->service releve du retrieval (Qdrant), pas
# d'une arete de graphe figee sur un score incertain.
with driver.session() as session:
    for f in faq_extra_service + faq_extra_general:
        session.run(
            "MERGE (faq:FAQ {{id: $id}}) SET faq += $props",
            id=f["id"],
            props={{
                "question_ar": f["question_ar"], "reponse_ar": f["reponse_ar"],
                "category": f.get("category", ""), "family": f.get("family", ""),
                "source": "data_faq",
            }},
        )
        for pcode in f.get("population_cible", []):
            session.run(
                "MATCH (faq:FAQ {{id: $id}}), (p:PopulationCible {{code: $pcode}}) MERGE (faq)-[:CIBLE]->(p)",
                id=f["id"], pcode=pcode,
            )
        for icode in f.get("institutions", []):
            session.run(
                "MATCH (faq:FAQ {{id: $id}}), (i:Institution {{code: $icode}}) MERGE (faq)-[:CONCERNE]->(i)",
                id=f["id"], icode=icode,
            )

    for ip in institution_enrich:
        session.run(
            "MATCH (i:Institution {{code: $code}}) SET i.profile_ar = $profile, i.profile_source = $source_id",
            code=ip["institution_code"], profile=ip["reponse_ar"], source_id=ip["source_id"],
        )

n_faq_extra = len(faq_extra_service) + len(faq_extra_general)
print(f"{{n_faq_extra}} FAQ (data_faq) creees/mises a jour, "
      f"{{len(institution_enrich)}} profils Institution enrichis")
''')

    nbformat.write(nb, path)
    print("05_Neo4j_Load: migre")


# ============================== 06_Qdrant_Index ==============================
def migrate_06_qdrant():
    path = f"{NB_DIR}/06_Qdrant_Index.ipynb"
    nb = nbformat.read(path, as_version=4)
    if already_migrated(nb):
        print("06_Qdrant_Index: deja migre, rien a faire")
        return

    patch_cell(
        nb,
        'faqs = {f["id"]: f for f in load_jsonl(PROCESSED_DIR / "faq_aos.jsonl")}',
        'faqs = {f["id"]: f for f in load_jsonl(PROCESSED_DIR / "faq_aos.jsonl")}\n\n'
        f'{MARKER}\n'
        '# Fusion avec les FAQ issues de data_faq (memes cles question_ar/reponse_ar\n'
        '# -> la branche FAQ de enrich_payload() plus bas fonctionne sans changement)\n'
        '# + profils Institution (nouvelle branche ajoutee plus bas).\n'
        'faqs.update({f["id"]: f for f in load_jsonl(PROCESSED_DIR / "faq_extra_service.jsonl")})\n'
        'faqs.update({f["id"]: f for f in load_jsonl(PROCESSED_DIR / "faq_extra_general.jsonl")})\n'
        'institution_profiles = {ip["institution_code"]: ip for ip in load_jsonl(PROCESSED_DIR / "institution_enrich.jsonl")}',
    )
    patch_cell(
        nb,
        'print(f"embeddings={len(embeddings)} services={len(services)} centres={len(centres)} "\n'
        '      f"programmes={len(programmes)} faq={len(faqs)}")',
        'print(f"embeddings={len(embeddings)} services={len(services)} centres={len(centres)} "\n'
        '      f"programmes={len(programmes)} faq={len(faqs)} institution_profiles={len(institution_profiles)}")',
    )

    insert_after(nb, "return enriched", f'''{MARKER}
def enrich_payload_institution(base: dict) -> dict:
    """Meme role que enrich_payload() pour entity_type == 'Institution' --
    fonction separee pour ne pas alourdir la cascade if/elif existante avec
    un cas qui n'existe pas encore dans le schema d'origine du guide."""
    entity_id = base.get("entity_id")
    enriched = dict(base)
    if entity_id in institution_profiles:
        ip = institution_profiles[entity_id]
        enriched.update({{"name": entity_id, "question": ip["question_ar"], "is_eps": False}})
    return enriched
''')

    patch_cell(
        nb,
        'enriched = enrich_payload(e["payload"])',
        f'{MARKER}\n'
        '    entity_type = e["payload"].get("entity_type")\n'
        '    enriched = enrich_payload_institution(e["payload"]) if entity_type == "Institution" else enrich_payload(e["payload"])',
    )

    nbformat.write(nb, path)
    print("06_Qdrant_Index: migre")


if __name__ == "__main__":
    migrate_02_chunk()
    migrate_05_neo4j()
    migrate_06_qdrant()
