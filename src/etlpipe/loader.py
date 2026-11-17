from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Optional, Protocol

import logging
import time
from rdflib import Graph

from .context import LoadContext
from .interfaces import Loader
from .projector import GraphProjector, NodeRow, PropertyGraphBatch, RelRow
from .report import LoadReport


SCHEMA_STATEMENTS = (
    "CREATE CONSTRAINT resource_uri IF NOT EXISTS FOR (r:Resource) REQUIRE r.uri IS UNIQUE",
    "CREATE INDEX work_celex IF NOT EXISTS FOR (w:Work) ON (w.celex)",
    "CREATE INDEX work_cellar_id IF NOT EXISTS FOR (w:Work) ON (w.cellarId)",
    "CREATE INDEX event_date IF NOT EXISTS FOR (e:Event) ON (e.eventDate)",
    "CREATE INDEX dossier_procedure_id IF NOT EXISTS FOR (d:Dossier) ON (d.procedureId)",
)

# alias list merge without APOC: append the new aliases that are not yet present
_MERGE_ALIASES = "SET n.alias = reduce(acc = coalesce(n.alias, []), a IN row.alias | CASE WHEN a IN acc THEN acc ELSE acc + a END)"

# Merge works that were first stored as two nodes under different identifiers (keeps the non-stub one first).
_RECONCILE_STATEMENTS = tuple(
    f"""
    MATCH (w:Work) WHERE w.{key} IS NOT NULL
    WITH w.{key} AS key, w ORDER BY w.stub ASC, w.uri
    WITH key, collect(w) AS nodes WHERE size(nodes) > 1
    CALL apoc.refactor.mergeNodes(nodes, {{properties: 'discard', mergeRels: false}}) YIELD node
    RETURN count(node) AS merged
    """
    for key in ("celex", "cellarId")
)

_LOAD_LOGGER_NAME = "etlpipe.load"

logger = logging.getLogger(_LOAD_LOGGER_NAME)


class DatabaseWriter(Protocol):
    """
    What the loader needs from the database wrapper (``Neo4jDatabase``).
    """
    def run_write(
        self,
        query: str,
        parameters: Optional[dict] = None
    ) -> dict[str, int]:
        """
        Run a write query in a managed transaction and return what it changed.

        Args:
            query (str): The Cypher query string.
            parameters (Optional[dict]): Optional dictionary of query parameters.

        Returns:
            dict[str, int]: Counters of the query summary (nodes_created, relationships_created, ...).
        """
        ...


def _chunks(
    rows: list,
    size: int
) -> Iterable[list]:
    """
    Split ``rows`` into consecutive chunks of at most ``size`` items.

    Args:
        rows (list): The rows to split.
        size (int): The maximum number of rows in a chunk.

    Yields:
        list: A chunk of rows.
    """
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


class Neo4jLoader(Loader):
    """
    Projects the canonical graph to nodes/relationships and writes them with ``UNWIND ... MERGE``.

    * node identity: ``:Resource {uri}`` (unique) - the same key neosemantics uses, so ontology/SKOS nodes imported by
      n10s share it;
    * relationship identity: ``(start, type, end, locator)`` - re-loading a document or loading overlapping documents
      never duplicates edges;
    * works that are only the end of a relation are written as *stubs* (``stub = true``) and are completed when their
      own document is loaded;
    * relationships are written grouped by type because Cypher cannot parametrise the relationship type.

    Args:
        db (Optional[DatabaseWriter]): Database wrapper with ``run_write`` (``Neo4jDatabase``). May be None when the loader
            is only used for dry runs (projection without writing); writing without it raises ``RuntimeError``. Default None.
        batch_size (int): Rows per transaction. Default 5000.
        reconcile_aliases (bool): After loading, merge works that ended up as two nodes because they were first seen
            under different identifiers (requires the APOC plugin; not covered by the automated tests). Default False.
        projector (Optional[GraphProjector]): Projector of the graph to nodes and relationships.
            Default ``GraphProjector()``.
    """

    def __init__(
        self,
        db: Optional[DatabaseWriter] = None,
        batch_size: int = 5000,
        reconcile_aliases: bool = False,
        projector: Optional[GraphProjector] = None
    ) -> None:
        self.db = db
        self.batch_size = batch_size
        self.reconcile_aliases = reconcile_aliases
        self.projector = projector or GraphProjector()
        self._schema_ready = False

    @property
    def _writer(self) -> DatabaseWriter:
        """
        The database wrapper used for writing.

        Raises:
            RuntimeError: If the loader was created without a database.
        """
        if self.db is None:
            raise RuntimeError("Neo4jLoader has no database: pass db=... or load with dry_run=True")
        return self.db

    def ensure_schema(self) -> None:
        """
        Create the constraints and indexes of the graph schema once per loader.
        """
        if self._schema_ready:
            return
        for statement in SCHEMA_STATEMENTS:
            self._writer.run_write(statement)
        self._schema_ready = True

    def load(
        self,
        graph: Graph,
        ctx: Optional[LoadContext] = None
    ) -> LoadReport:
        ctx = ctx or LoadContext()
        started = time.perf_counter()
        batch = self.projector.project(graph)
        report = LoadReport(
            nodes_projected=len(batch.nodes),
            relationships_projected=len(batch.relationships),
            nodes_by_kind=batch.nodes_by_kind(),
            relationships_by_type=batch.relationships_by_type(),
            dry_run=ctx.dry_run,
            warnings=list(batch.warnings),
        )
        if not ctx.dry_run:
            self.ensure_schema()
            self._write_nodes(batch, ctx, report)
            self._write_relationships(batch, report)
            if self.reconcile_aliases:
                self._reconcile(report)
        report.duration_s = time.perf_counter() - started
        logger.info("[%s] load: %s nodes, %s relationships%s %s in %.2fs", ctx.source or "-", f"{report.nodes_projected:,}",
                    f"{report.relationships_projected:,}", " (dry run)" if ctx.dry_run else "",
                    dict(report.db_counters) if report.db_counters else "", report.duration_s)
        for w in report.warnings:
            logger.warning("[%s] load: %s", ctx.source or "-", w)
        return report

    # ---- nodes -------------------------------------------------------------------------------------------------------
    @staticmethod
    def node_statement(
        kind: str,
        labels: tuple[str, ...],
        stub: bool
    ) -> str:
        """
        Build the Cypher statement that merges one group of nodes.

        Args:
            kind (str): The node kind (primary label), e.g. ``Work``.
            labels (tuple[str, ...]): The additional labels of the nodes.
            stub (bool): Whether the nodes are stubs (works that are only the end of a relation).

        Returns:
            str: The parametrised ``UNWIND ... MERGE`` statement.
        """
        label_clause = ":".join((kind,) + labels)
        if kind == "Work" and not stub:
            return (f"UNWIND $rows AS row MERGE (n:Resource {{uri: row.uri}}) SET n:{label_clause} SET n += row.props "
                    f"SET n.stub = false, n.loadedFrom = $source {_MERGE_ALIASES}")
        on_create = "ON CREATE SET n.stub = true " if kind == "Work" else ""
        return (f"UNWIND $rows AS row MERGE (n:Resource {{uri: row.uri}}) {on_create}SET n:{label_clause} SET n += row.props "
                f"{_MERGE_ALIASES}")

    def _write_nodes(
        self,
        batch: PropertyGraphBatch,
        ctx: LoadContext,
        report: LoadReport
    ) -> None:
        """
        Write the projected nodes, grouped by kind, labels and stub flag.

        Args:
            batch (PropertyGraphBatch): The projected property graph.
            ctx (LoadContext): The loading context.
            report (LoadReport): The report updated with the database counters.
        """
        groups: dict[tuple, list[NodeRow]] = defaultdict(list)
        for node in batch.nodes:
            groups[(node.kind, node.labels, node.stub)].append(node)
        for (kind, labels, stub), nodes in groups.items():
            statement = self.node_statement(kind, labels, stub)
            rows = [{"uri": n.uri, "props": n.props, "alias": n.alias} for n in nodes]
            for chunk in _chunks(rows, self.batch_size):
                self._run(statement, {"rows": chunk, "source": ctx.source}, report)

    # ---- relationships -----------------------------------------------------------------------------------------------
    @staticmethod
    def relationship_statement(
        rel_type: str
    ) -> str:
        """
        Build the Cypher statement that merges the relationships of one type.

        Args:
            rel_type (str): The relationship type.

        Returns:
            str: The parametrised ``UNWIND ... MERGE`` statement.
        """
        return ("UNWIND $rows AS row MATCH (a:Resource {uri: row.start}), (b:Resource {uri: row.end}) "
                f"MERGE (a)-[r:`{rel_type}` {{locator: row.locator}}]->(b) SET r += row.props")

    def _write_relationships(
        self,
        batch: PropertyGraphBatch,
        report: LoadReport
    ) -> None:
        """
        Write the projected relationships, grouped by type.

        Args:
            batch (PropertyGraphBatch): The projected property graph.
            report (LoadReport): The report updated with the database counters.
        """
        by_type: dict[str, list[RelRow]] = defaultdict(list)
        for rel in batch.relationships:
            by_type[rel.type].append(rel)
        for rel_type, rels in by_type.items():
            statement = self.relationship_statement(rel_type)
            rows = [{"start": r.start, "end": r.end, "locator": r.locator, "props": r.props} for r in rels]
            for chunk in _chunks(rows, self.batch_size):
                self._run(statement, {"rows": chunk}, report)

    # ---- helpers -----------------------------------------------------------------------------------------------------
    def _run(
        self,
        statement: str,
        parameters: dict[str, Any],
        report: LoadReport
    ) -> None:
        """
        Run one write statement and add its counters to the report.

        Args:
            statement (str): The Cypher statement.
            parameters (dict[str, Any]): The statement parameters.
            report (LoadReport): The report updated with the database counters.
        """
        counters = self._writer.run_write(statement, parameters)
        report.batches += 1
        for key, value in counters.items():
            if value:
                report.db_counters[key] += value

    def _reconcile(
        self,
        report: LoadReport
    ) -> None:
        """
        Merge works that were stored as two nodes under different identifiers (requires APOC).

        Args:
            report (LoadReport): The report updated with the merge counters or a warning when APOC is missing.
        """
        for statement in _RECONCILE_STATEMENTS:
            try:
                counters = self._writer.run_write(statement)
            except Exception as exc:  # APOC missing or not permitted
                report.warnings.append(f"alias reconciliation skipped: {exc}")
                return
            if counters.get("nodes_deleted"):
                report.db_counters["nodes_merged"] += counters["nodes_deleted"]