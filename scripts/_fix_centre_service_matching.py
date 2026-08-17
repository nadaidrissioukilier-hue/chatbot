#!/usr/bin/env python3
"""Correctif ponctuel de 03_Match.ipynb (2026-08-14) : le matching
"population_commune" ne matchait JAMAIS personnes_agees/personnes_handicapees
malgre 66+372 centres explicitement taggues pour ces populations. Cause :
centres_normalized.jsonl:personnes_cibles n'a que 5 valeurs distinctes, en
FRANCAIS ABREGE ("Pers. en sit . hand.", "Pers. âgés en sit. diff."), qui ne
contiennent ni le slug categorie ("personnes_handicapees") ni le libelle
complet AR/FR ("Personnes Handicapées") que le check generique cherchait.

Idempotent (marqueur unique verifie avant patch).
"""
import nbformat

MARKER = "# === FIX_POPULATION_COMMUNE_2026_08_14 ==="
PATH = "/home/ubunto/entraide-mvp/notebooks/03_Match.ipynb"


def patch_cell(nb, old_substring, new_substring):
    matches = [c for c in nb.cells if c.cell_type == "code" and "".join(c.source).count(old_substring) == 1]
    if len(matches) != 1:
        raise RuntimeError(f"Anchor trouve dans {len(matches)} cellule(s) (attendu 1): {old_substring!r}")
    cell = matches[0]
    src = "".join(cell.source) if isinstance(cell.source, list) else cell.source
    cell.source = src.replace(old_substring, new_substring)


def main():
    nb = nbformat.read(PATH, as_version=4)
    if any(MARKER in "".join(c.get("source", "")) for c in nb.cells):
        print("Deja corrige, rien a faire")
        return

    old = '''TOP_N_PER_CENTRE = 8
MAX_EPS_PER_CENTRE = 2  # EPS = dernier recours : jamais plus de 2/8 relations


def score_centre_service(centre: dict, service: dict):
    c_inst = set(centre["institutions"])
    s_inst = set(service["institutions"])
    common = c_inst & s_inst

    if common - {"EPS"}:
        return 1.00, "exact_institution"
    if common == {"EPS"}:
        return 0.50, "eps_fallback"

    pop_text = normalize_arabic(centre.get("personnes_cibles", ""))
    service_pop = POPULATION_CIBLES.get(service["categorie"], {})
    if pop_text and any(normalize_arabic(kw) in pop_text for kw in [service["categorie"], service_pop.get("ar", ""), service_pop.get("fr", "")] if kw):
        return 0.75, "population_commune"

    return 0.0, None'''

    new = '''TOP_N_PER_CENTRE = 8
MAX_EPS_PER_CENTRE = 2  # EPS = dernier recours : jamais plus de 2/8 relations

''' + MARKER + '''
# centres_normalized.jsonl:personnes_cibles n'a QUE 5 valeurs distinctes
# (verifie sur les 3328 centres), en francais abrege -- le check generique
# par sous-chaine (slug categorie ou libelle complet AR/FR) ne matchait
# JAMAIS "Pers. en sit . hand." ni "Pers. âgés en sit. diff.", laissant
# personnes_handicapees (372 centres taggues) et personnes_agees (66
# centres) a 0 relation Centre->Service malgre des donnees population
# explicites (trouve en audit le 2026-08-14). Mapping explicite plutot que
# d'elargir le check generique : les valeurs sont fixes et connues (5 au
# total), un mapping exact est plus fiable qu'un matching flou supplementaire.
_PERSONNES_CIBLES_MAP = {
    "enfants en sit. diff.": "enfants",
    "femmes en sit. diff.": "femmes",
    "pers. en sit . hand.": "personnes_handicapees",
    "pers. âgés en sit. diff.": "personnes_agees",
    # "tc" (351 centres) : signification ambigue dans la source (non
    # documentee), laisse sans mapping plutot que de deviner -- ces centres
    # restent eligibles via exact_institution/eps_fallback normalement.
}


def score_centre_service(centre: dict, service: dict):
    c_inst = set(centre["institutions"])
    s_inst = set(service["institutions"])
    common = c_inst & s_inst

    if common - {"EPS"}:
        return 1.00, "exact_institution"

    pop_text = normalize_arabic(centre.get("personnes_cibles", ""))
    mapped_category = _PERSONNES_CIBLES_MAP.get(pop_text)
    if mapped_category and mapped_category == service["categorie"]:
        return 0.75, "population_commune"

    service_pop = POPULATION_CIBLES.get(service["categorie"], {})
    if pop_text and any(normalize_arabic(kw) in pop_text for kw in [service["categorie"], service_pop.get("ar", ""), service_pop.get("fr", "")] if kw):
        return 0.75, "population_commune"

    if common == {"EPS"}:
        return 0.50, "eps_fallback"

    return 0.0, None'''

    patch_cell(nb, old, new)
    nbformat.write(nb, PATH)
    print("03_Match.ipynb corrige")


if __name__ == "__main__":
    main()
