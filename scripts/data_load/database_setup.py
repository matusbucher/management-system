"""
Preparation of an empty Neo4j database for the knowledge graph: schema, neosemantics (n10s) configuration, the CDM ontology and
the labels of the reference data (EuroVoc concepts, authority tables), plus the statistics of what is in the database.

Every step is idempotent, so the preparation can be repeated on a database that is already (partly) set up.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from src.etlpipe.loader import SCHEMA_STATEMENTS
from src.etlpipe.neo4j_database import Neo4jDatabase
from src.eurlex.sparql_api import SparqlAPI

logger = logging.getLogger("etlpipe.populate.setup")

ROOT = Path(__file__).resolve().parents[2]
CDM_DIR = ROOT / "data" / "cdm"

# The CDM ontology files imported by default. cdm_annotationproperties.rdf is not listed: n10s parses its 259 triples but loads none of them.
DEFAULT_ONTOLOGY_FILES = ("cdm.rdf",)

# The graph configuration of n10s (kept here so that a fresh database is reproducible); see docs/ETL_TRANSFORMER_LOADER_STRATEGY.md section 6.
N10S_GRAPH_CONFIG = {
    "handleVocabUris": "SHORTEN",
    "handleMultival": "ARRAY",
    "keepLangTag": True,
    "handleRDFTypes": "LABELS",
}

# Label prefix n10s gives to the ontology nodes (classes, relationships, properties) with the configuration above.
ONTOLOGY_LABELS = {
    "classes": "n4sch__Class",
    "relationships": "n4sch__Relationship",
    "properties": "n4sch__Property",
}

_LABEL_CHUNK_SIZE = 60  # the SPARQL endpoint rejects requests above about 6 KB


class DatabaseSetup:
    """
    Sets up and inspects the Neo4j database of the knowledge graph.

    Args:
        db (Neo4jDatabase): The database wrapper.
        cdm_dir (Path): Directory with the CDM ontology files. Default ``data/cdm``.
    """

    def __init__(
        self,
        db: Neo4jDatabase,
        cdm_dir: Path = CDM_DIR
    ) -> None:
        self.db = db
        self.cdm_dir = cdm_dir

    # ---- environment -------------------------------------------------------------------------------------------------
    def check_environment(self) -> dict[str, Any]:
        """
        Check the server and the plugins the population depends on.

        Returns:
            dict[str, Any]: ``server`` (name, version, edition), ``n10s`` (version), ``apoc`` (version or None) and the
                number of nodes and relationships already in the database.

        Raises:
            RuntimeError: If the neosemantics plugin is not installed.
        """
        component = self.db.run_query("CALL dbms.components() YIELD name, versions, edition RETURN name, versions[0] AS version, edition")[0]
        n10s = self._version("RETURN n10s.version() AS version")
        if n10s is None:
            raise RuntimeError("The neosemantics (n10s) plugin is not installed: the CDM ontology cannot be imported")
        counts = self.db.run_query("MATCH (n) RETURN count(n) AS nodes")[0]
        relationships = self.db.run_query("MATCH ()-[r]->() RETURN count(r) AS relationships")[0]
        return {
            "server": component,
            "n10s": n10s,
            "apoc": self._version("RETURN apoc.version() AS version"),
            "nodes": counts["nodes"],
            "relationships": relationships["relationships"],
        }

    def _version(
        self,
        query: str
    ) -> Optional[str]:
        """
        Run a query that returns the version of a plugin.

        Args:
            query (str): Query with a ``version`` column.

        Returns:
            Optional[str]: The version, or None if the plugin function is not available.
        """
        try:
            return self.db.run_query(query)[0]["version"]
        except Exception:
            return None

    # ---- schema, n10s, ontology --------------------------------------------------------------------------------------
    def ensure_schema(self) -> list[str]:
        """
        Create the constraint and indexes of the graph schema (the same statements the loader uses).

        Returns:
            list[str]: Names of the constraints and indexes in the database afterwards.
        """
        for statement in SCHEMA_STATEMENTS:
            self.db.run_write(statement)
        names = [row["name"] for row in self.db.run_query("SHOW CONSTRAINTS YIELD name RETURN name")]
        names += [row["name"] for row in self.db.run_query("SHOW INDEXES YIELD name, type WHERE type <> 'LOOKUP' RETURN name")]
        return sorted(names)

    def configure_n10s(self) -> bool:
        """
        Initialise the neosemantics graph configuration, unless the database has one already.

        Returns:
            bool: True if the configuration was created, False if it existed.
        """
        if self.db.run_query("CALL n10s.graphconfig.show()"):
            return False
        has_data = bool(self.db.run_query("MATCH (n) RETURN n LIMIT 1"))
        self.db.run_query("CALL n10s.graphconfig.init($config)", {"config": {**N10S_GRAPH_CONFIG, "force": has_data}})
        return True

    def ontology_counts(self) -> dict[str, int]:
        """
        Count the imported ontology nodes.

        Returns:
            dict[str, int]: Number of classes, relationships and properties.
        """
        return {
            name: self.db.run_query(f"MATCH (n:`{label}`) RETURN count(n) AS n")[0]["n"]
            for name, label in ONTOLOGY_LABELS.items()
        }

    def import_ontology(
        self,
        files: Iterable[str] = DEFAULT_ONTOLOGY_FILES,
        force: bool = False
    ) -> dict[str, Any]:
        """
        Import the CDM ontology files with neosemantics, unless an ontology is imported already.

        Args:
            files (Iterable[str]): File names in the CDM directory. Default ``DEFAULT_ONTOLOGY_FILES``.
            force (bool): Import again even if the database has an ontology (the import is a merge). Default False.

        Returns:
            dict[str, Any]: ``imported`` (bool), ``files`` (triples parsed and loaded per file) and ``counts`` of the ontology nodes.
        """
        before = self.ontology_counts()
        if before["classes"] and not force:
            return {"imported": False, "files": {}, "counts": before}
        per_file: dict[str, Any] = {}
        for name in files:
            started = time.perf_counter()
            row = self.db.run_query("CALL n10s.onto.import.inline($rdf, 'RDF/XML')", {"rdf": (self.cdm_dir / name).read_text(encoding="utf-8")})[0]
            if row["terminationStatus"] != "OK":
                raise RuntimeError(f"Import of {name} failed: {row}")
            per_file[name] = {
                "triples_parsed": row["triplesParsed"],
                "triples_loaded": row["triplesLoaded"],
                "duration_s": round(time.perf_counter() - started, 2),
            }
        return {"imported": True, "files": per_file, "counts": self.ontology_counts()}

    # ---- reference data labels ---------------------------------------------------------------------------------------
    def enrich_labels(
        self,
        sparql: Optional[SparqlAPI] = None
    ) -> dict[str, int]:
        """
        Set the English label (``skos:prefLabel``) of the concepts and institutions that have none, using the SPARQL endpoint.

        The dumps carry only the URIs of EuroVoc concepts and authority table entries, so the graph would show opaque
        identifiers without this step.

        Args:
            sparql (Optional[SparqlAPI]): SPARQL endpoint wrapper. Default ``SparqlAPI()``.

        Returns:
            dict[str, int]: ``missing`` (nodes without a label before), ``labelled`` (nodes that got a label) and ``unresolved``.
        """
        sparql = sparql or SparqlAPI()
        uris = [row["uri"] for row in self.db.run_query(
            "MATCH (n:Resource) WHERE (n:Concept OR n:Institution) AND n.label IS NULL RETURN n.uri AS uri ORDER BY uri"
        )]
        labelled = 0
        for chunk in _chunks(uris, _LABEL_CHUNK_SIZE):
            values = " ".join(f"<{uri}>" for uri in chunk)
            query = (
                "PREFIX skos: <http://www.w3.org/2004/02/skos/core#> "
                f"SELECT ?c (SAMPLE(?l) AS ?label) WHERE {{ VALUES ?c {{ {values} }} ?c skos:prefLabel ?l FILTER(lang(?l) = 'en') }} GROUP BY ?c"
            )
            rows = [{"uri": row["c"], "label": row["label"]} for row in sparql.select(query)]
            if rows:
                counters = self.db.run_write("UNWIND $rows AS row MATCH (n:Resource {uri: row.uri}) SET n.label = row.label", {"rows": rows})
                labelled += len(rows)
                logger.debug("labels: %d of %d set (%s)", len(rows), len(chunk), counters)
        return {"missing": len(uris), "labelled": labelled, "unresolved": len(uris) - labelled}

    # ---- reset -------------------------------------------------------------------------------------------------------
    def reset(self) -> dict[str, int]:
        """
        Delete all nodes and relationships; constraints and indexes are kept.

        The neosemantics graph configuration is a node too, so it is deleted with the rest and created again by ``configure_n10s``.

        Returns:
            dict[str, int]: Number of nodes that were deleted.
        """
        nodes = self.db.run_query("MATCH (n) RETURN count(n) AS n")[0]["n"]
        self.db.run_query("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS")
        return {"nodes_deleted": nodes}

    # ---- statistics --------------------------------------------------------------------------------------------------
    def statistics(
        self,
        requested: Optional[list[str]] = None
    ) -> dict[str, Any]:
        """
        Collect the statistics of the knowledge graph in the database.

        Args:
            requested (Optional[list[str]]): Cellar work IDs that were meant to be loaded; if given, the statistics tell
                how many of them are in the database as works with their own metadata.

        Returns:
            dict[str, Any]: Counts of nodes per label and relationships per type, works (loaded and stubs), the ontology,
                the most connected works and the number of works that exist twice under different identifiers.
        """
        run = self.db.run_query
        ontology_prefix = "n4sch__"
        graph_nodes = "n:Resource AND NOT any(l IN labels(n) WHERE l STARTS WITH $prefix)"
        labels = {
            row["label"]: row["n"]
            for row in run(f"MATCH (n) WHERE {graph_nodes} UNWIND labels(n) AS label RETURN label, count(*) AS n ORDER BY n DESC",
                           {"prefix": ontology_prefix})
        }
        nodes = run(f"MATCH (n) WHERE {graph_nodes} RETURN count(n) AS n", {"prefix": ontology_prefix})[0]["n"]
        relationships = {
            row["type"]: row["n"]
            for row in run("MATCH (:Resource)-[r]->(:Resource) WHERE NOT type(r) STARTS WITH $prefix RETURN type(r) AS type, count(r) AS n ORDER BY n DESC",
                           {"prefix": ontology_prefix})
        }
        works = {
            ("stub" if row["stub"] else "loaded"): row["n"]
            for row in run("MATCH (w:Work) RETURN coalesce(w.stub, false) AS stub, count(w) AS n")
        }
        most_connected = run(
            "MATCH (w:Work)-[r]-() WHERE NOT type(r) STARTS WITH $prefix "
            "RETURN w.celex AS celex, w.uri AS uri, count(r) AS degree ORDER BY degree DESC LIMIT 10",
            {"prefix": ontology_prefix},
        )
        duplicates = run("MATCH (w:Work) WHERE w.celex IS NOT NULL WITH w.celex AS celex, count(*) AS n WHERE n > 1 RETURN count(*) AS n")[0]["n"]
        present = None
        if requested is not None:
            present = run("MATCH (w:Work) WHERE w.cellarId IN $ids AND coalesce(w.stub, false) = false RETURN count(w) AS n", {"ids": requested})[0]["n"]
        return {
            "requested_works": {"listed": len(requested), "present": present} if requested is not None else None,
            "nodes_by_label": labels,
            "relationships_by_type": relationships,
            "nodes": nodes,
            "relationships": sum(relationships.values()),
            "works": works,
            "ontology": self.ontology_counts(),
            "most_connected_works": most_connected,
            "works_duplicated_by_celex": duplicates,
        }


def _chunks(
    items: list[str],
    size: int
) -> Iterator[list[str]]:
    """
    Split a list into consecutive chunks.

    Args:
        items (list[str]): The items to split.
        size (int): The maximum size of a chunk.

    Yields:
        list[str]: The next chunk.
    """
    for start in range(0, len(items), size):
        yield items[start:start + size]
