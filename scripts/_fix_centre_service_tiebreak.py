#!/usr/bin/env python3
"""Deuxieme correctif de 03_Match.ipynb (2026-08-14) : meme apres le fix du
mapping personnes_cibles, 22 services restent orphelins (14
personnes_handicapees, 3 personnes_agees, 5 femmes). Cause : quand des
CENTAINES de centres partagent le meme score (0.75) pour TOUS les services
de leur categorie, le tri stable de Python conserve l'ordre original du
fichier -> TOUS ces centres selectionnent les 8 PREMIERS services de la
categorie (limite TOP_N_PER_CENTRE), et les services suivants dans le
fichier ne sont jamais choisis par AUCUN centre (22 handicap - 8 = 14
orphelins ; 11 agees - 8 = 3 orphelins -- correspond exactement).

Fix : departage des egalites par un hash deterministe (centre_id, service_id)
plutot que l'ordre de fichier -- chaque centre "voit" un ordre different
parmi les candidats a egalite, repartissant les selections sur l'ensemble
des services au lieu de toujours privilegier les memes premiers.
"""
import nbformat

MARKER = "# === FIX_TIEBREAK_2026_08_14 ==="
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

    old = '''    candidates.sort(key=lambda x: x[1], reverse=True)'''
    new = MARKER + '''
    # Depart les egalites par hash deterministe (centre_id, service_id) --
    # sans ca, des centaines de centres a score identique (0.75) selectionnent
    # tous les 8 PREMIERS services du fichier (ordre stable), laissant les
    # suivants orphelins pour toujours. Deterministe -> idempotent (memes
    # entrees, meme resultat a chaque execution), contrairement a un tri
    # aleatoire non reproductible.
    import hashlib as _hashlib

    def _tie_key(service_id):
        return _hashlib.md5(f"{centre['id']}_{service_id}".encode()).hexdigest()

    candidates.sort(key=lambda x: (x[1], _tie_key(x[0])), reverse=True)'''

    patch_cell(nb, old, new)
    nbformat.write(nb, PATH)
    print("03_Match.ipynb corrige (tie-break)")


if __name__ == "__main__":
    main()
