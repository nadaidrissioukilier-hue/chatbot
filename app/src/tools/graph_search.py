"""Recherche graphe : expansion via les relations réelles du schéma
(OFFRE, CIBLE, ABRITE_DANS, S_APPUIE_SUR, REPOND_A) et hiérarchie
géographique (Region -> Delegation -> Commune -> Centre).

Corrige 3 bugs v1 :
- seeds passés par `WHERE ID(node) IN $ids` (ID interne Neo4j), alors que les
  seeds réellement disponibles (retour de vector_search) sont des `entity_id`
  métier (ex: "centre_d25f2ceb602f") -> on matche maintenant sur la
  propriété `id`, la même utilisée comme clé dans Qdrant.
- noms de relations demandés (OFFRE_PAR, LOCALISE_DANS...) qui n'existent
  pas dans le graphe réel -> alignés sur OFFRE/CIBLE/ABRITE_DANS/S_APPUIE_SUR.
- expansion géographique par latitude/longitude alors que ces champs
  n'existent pas du tout dans les données -> remplacée par une expansion
  par hiérarchie administrative réelle (même commune/délégation/région).
"""
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase

from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, TOP_K_GRAPH


class GraphSearch:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def expand_offre(self, seed_ids: List[str]) -> List[Dict[str, Any]]:
        """Centre <-> Service via OFFRE (dans les deux sens : un seed peut être
        un Centre (-> Services offerts) ou un Service (-> Centres qui l'offrent))."""
        query = """
        MATCH (seed) WHERE seed.id IN $ids
        MATCH (seed)-[r:OFFRE]-(other)
        RETURN DISTINCT other.id AS id, labels(other)[0] AS label,
               properties(other) AS data, r.score AS score
        ORDER BY score DESC
        LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(query, ids=seed_ids, limit=TOP_K_GRAPH)
            return [
                {"id": r["id"], "label": r["label"], "data": r["data"],
                 "score": (r["score"] or 50) / 100.0, "relation_type": "offre"}
                for r in result
            ]

    def expand_cible(self, seed_ids: List[str]) -> List[Dict[str, Any]]:
        """Service/Programme <-> PopulationCible via CIBLE."""
        query = """
        MATCH (seed) WHERE seed.id IN $ids
        MATCH (seed)-[:CIBLE]-(pop:PopulationCible)
        RETURN DISTINCT pop.code AS id, 'PopulationCible' AS label,
               properties(pop) AS data
        LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(query, ids=seed_ids, limit=TOP_K_GRAPH)
            return [
                {"id": r["id"], "label": r["label"], "data": r["data"],
                 "score": 1.0, "relation_type": "cible"}
                for r in result
            ]

    def expand_geo(self, seed_ids: List[str]) -> List[Dict[str, Any]]:
        """Centres voisins : même commune, puis même délégation, en repli
        même région — reflète la hiérarchie stricte du guide."""
        query = """
        MATCH (seed:Centre) WHERE seed.id IN $ids
        MATCH (nearby:Centre)
        WHERE nearby.id <> seed.id
          AND (nearby.commune = seed.commune
               OR nearby.delegation = seed.delegation
               OR nearby.region = seed.region)
        RETURN DISTINCT nearby.id AS id, 'Centre' AS label, properties(nearby) AS data,
               CASE WHEN nearby.commune = seed.commune THEN 1.0
                    WHEN nearby.delegation = seed.delegation THEN 0.6
                    ELSE 0.3 END AS score
        ORDER BY score DESC
        LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(query, ids=seed_ids, limit=TOP_K_GRAPH)
            return [
                {"id": r["id"], "label": r["label"], "data": r["data"],
                 "score": r["score"], "relation_type": "geo"}
                for r in result
            ]

    def expand_by_region(self, region_name: str, population_types: Optional[List[str]] = None, limit: int = 30) -> List[Dict[str, Any]]:
        """Ancrage géographique DIRECT (2026-08-14) : centres de la région
        EXACTE demandée, sans dépendre d'un seed déjà trouvé par la
        recherche vectorielle (contrairement à expand_geo, qui part d'un
        centre déjà identifié et ne trouve que son voisinage -- rate la
        bonne région si aucun résultat vectoriel initial n'y était).
        `region_name` doit déjà être résolu vers un nom canonique (voir
        src/tools/geo_resolver.py) -- correspondance exacte sur Centre.region.

        Priorise les centres qui offrent EFFECTIVEMENT un service de la/les
        population(s) demandée(s) (via OFFRE -> Service.categorie) : sans ce
        tri, `LIMIT` coupait au hasard et laissait de côté les centres
        pertinents au profit de centres de la région mais hors-sujet (ex:
        "SOS jeunesse" remonté sur une question personnes âgées -- trouvé en
        test réel le 2026-08-14)."""
        query = """
        MATCH (c:Centre {region: $region})
        OPTIONAL MATCH (c)-[:OFFRE]->(s:Service) WHERE $population_types = [] OR s.categorie IN $population_types
        WITH c, count(s) AS pop_match
        RETURN c.id AS id, 'Centre' AS label, properties(c) AS data, pop_match
        ORDER BY pop_match DESC
        LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(query, region=region_name, population_types=population_types or [], limit=limit)
            return [
                {"id": r["id"], "label": r["label"], "data": r["data"],
                 # 1.0 si le centre offre reellement la population demandee,
                 # 0.6 sinon (juste "dans la region", signal geo plus faible
                 # mais toujours superieur a un centre hors-region).
                 "score": 1.0 if r["pop_match"] > 0 else 0.6, "relation_type": "geo"}
                for r in result
            ]

    def expand_appuie(self, seed_ids: List[str]) -> List[Dict[str, Any]]:
        """Programme <-> Institution via S_APPUIE_SUR."""
        query = """
        MATCH (seed) WHERE seed.id IN $ids
        MATCH (seed)-[:S_APPUIE_SUR]-(inst:Institution)
        RETURN DISTINCT inst.code AS id, 'Institution' AS label, properties(inst) AS data
        LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(query, ids=seed_ids, limit=TOP_K_GRAPH)
            return [
                {"id": r["id"], "label": r["label"], "data": r["data"],
                 "score": 1.0, "relation_type": "appuie"}
                for r in result
            ]

    def expand_repond_a(self, seed_ids: List[str]) -> List[Dict[str, Any]]:
        """FAQ <-> Programme via REPOND_A."""
        query = """
        MATCH (seed) WHERE seed.id IN $ids
        MATCH (seed)-[:REPOND_A]-(other)
        RETURN DISTINCT other.id AS id, labels(other)[0] AS label, properties(other) AS data
        LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(query, ids=seed_ids, limit=TOP_K_GRAPH)
            return [
                {"id": r["id"], "label": r["label"], "data": r["data"],
                 "score": 1.0, "relation_type": "repond_a"}
                for r in result
            ]

    def smart_expansion(
        self, seed_ids: List[str], relations: List[str], filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Expande selon les types de relations demandées par le ToolPlanner
        (noms alignés sur le schéma réel, voir scripts/load_neo4j.py)."""
        if not seed_ids:
            return []

        dispatch = {
            "OFFRE": self.expand_offre,
            "CIBLE": self.expand_cible,
            "ABRITE_DANS": self.expand_geo,
            "S_APPUIE_SUR": self.expand_appuie,
            "REPOND_A": self.expand_repond_a,
        }

        results = []
        for relation in relations:
            handler = dispatch.get(relation)
            if handler:
                results.extend(handler(seed_ids))

        unique = {r["id"]: r for r in results if r.get("id")}
        ranked = sorted(unique.values(), key=lambda x: x["score"], reverse=True)
        return ranked[:TOP_K_GRAPH]

    def close(self):
        self.driver.close()
