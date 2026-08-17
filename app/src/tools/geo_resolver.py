"""Résolution ville/région (texte libre AR/FR) -> nom de région canonique
Neo4j (2026-08-14, "aller plus loin sur le score géographique").

Ancrage géographique DIRECT, complémentaire à
graph_search.GraphSearch.expand_geo() : celui-ci ne trouve que le voisinage
d'un centre DEJA trouvé par la recherche vectorielle -- indirect, et rate la
bonne région si aucun des 5 premiers résultats vectoriels n'est déjà dans la
bonne zone (vérifié en test réel : "...قريب مني انا اسكن بالرباط" ne
remontait des centres pertinents qu'accessoirement, le reste du top restait
dispersé sur d'autres régions). Ici, dès qu'une ville/région est repérée
dans la question (même vocabulaire que intent_router.py:entity_keywords,
tenu synchronisé), on va chercher les centres de CETTE région précise
directement dans Neo4j, sans dépendre de ce que la recherche vectorielle a
trouvé en premier.

Les 12 noms de région ci-dessous sont les valeurs EXACTES stockées dans
Neo4j (Region.name / Centre.region), vérifiées par requête directe."""

CITY_TO_REGION = {
    "tanger-tétouan-al hoceïma": "Tanger-Tétouan-Al Hoceïma",
    "tanger": "Tanger-Tétouan-Al Hoceïma",
    "tétouan": "Tanger-Tétouan-Al Hoceïma",
    "al hoceïma": "Tanger-Tétouan-Al Hoceïma",
    "طنجة": "Tanger-Tétouan-Al Hoceïma",

    "l'oriental": "L'Oriental",
    "oriental": "L'Oriental",
    "oujda": "L'Oriental",
    "nador": "L'Oriental",
    "وجدة": "L'Oriental",

    "fès-meknès": "Fès-Meknès",
    "fès": "Fès-Meknès",
    "fes": "Fès-Meknès",
    "meknès": "Fès-Meknès",
    "meknes": "Fès-Meknès",
    "taza": "Fès-Meknès",
    "فاس": "Fès-Meknès",

    "rabat-salé-kénitra": "Rabat-Salé-Kénitra",
    "rabat": "Rabat-Salé-Kénitra",
    "salé": "Rabat-Salé-Kénitra",
    "sale": "Rabat-Salé-Kénitra",
    "kénitra": "Rabat-Salé-Kénitra",
    "kenitra": "Rabat-Salé-Kénitra",
    "khémisset": "Rabat-Salé-Kénitra",
    "khemisset": "Rabat-Salé-Kénitra",
    "الرباط": "Rabat-Salé-Kénitra",
    "سلا": "Rabat-Salé-Kénitra",

    "béni mellal-khénifra": "Béni Mellal-Khénifra",
    "béni mellal": "Béni Mellal-Khénifra",
    "beni mellal": "Béni Mellal-Khénifra",
    "khénifra": "Béni Mellal-Khénifra",
    "khouribga": "Béni Mellal-Khénifra",

    "casablanca-settat": "Casablanca-Settat",
    "casablanca": "Casablanca-Settat",
    "settat": "Casablanca-Settat",
    "berrechid": "Casablanca-Settat",
    "el jadida": "Casablanca-Settat",
    "mohammedia": "Casablanca-Settat",
    "الدار البيضاء": "Casablanca-Settat",

    "marrakech-safi": "Marrakech-Safi",
    "marrakech": "Marrakech-Safi",
    "safi": "Marrakech-Safi",
    "essaouira": "Marrakech-Safi",
    "مراكش": "Marrakech-Safi",

    "drâa-tafilalet": "Drâa-Tafilalet",
    "drâa": "Drâa-Tafilalet",
    "tafilalet": "Drâa-Tafilalet",
    "errachidia": "Drâa-Tafilalet",
    "ouarzazate": "Drâa-Tafilalet",
    "midelt": "Drâa-Tafilalet",

    "souss-massa": "Souss-Massa",
    "agadir": "Souss-Massa",
    "taroudant": "Souss-Massa",
    "tiznit": "Souss-Massa",
    "أكادير": "Souss-Massa",

    "guelmim-oued noun": "Guelmim-Oued Noun",
    "guelmim": "Guelmim-Oued Noun",
    "tan-tan": "Guelmim-Oued Noun",

    "laâyoune-sakia el hamra": "Laâyoune-Sakia El Hamra",
    "laâyoune": "Laâyoune-Sakia El Hamra",
    "laayoune": "Laâyoune-Sakia El Hamra",

    "dakhla-oued ed-dahab": "Dakhla-Oued Ed-Dahab",
    "dakhla": "Dakhla-Oued Ed-Dahab",

    # "المغرب" (Maroc, le pays entier) volontairement absent : aucune
    # région precise ne peut en être déduite, un mauvais mapping serait
    # pire qu'aucun mapping (filtrerait tout le pays sur UNE région au hasard).
}


def resolve_region(text: str) -> str:
    """Retourne le nom de région canonique Neo4j, ou "" si non reconnu."""
    return CITY_TO_REGION.get((text or "").strip().lower(), "")


def resolve_regions(texts) -> list:
    """Résout une liste de mentions ville/région (dédupliquées, dans l'ordre
    d'apparition) -- une question peut mentionner plusieurs villes."""
    seen, out = set(), []
    for t in texts or []:
        region = resolve_region(t)
        if region and region not in seen:
            seen.add(region)
            out.append(region)
    return out
