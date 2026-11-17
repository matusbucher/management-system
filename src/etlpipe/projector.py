"""
Projection of the canonical work graph to property-graph rows (nodes and relationships). Pure, no database access.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from frozendict import frozendict
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from .constants import KMS, K_ALIAS, K_DOC_TYPE, K_LOCATOR, K_STUB, KMS_WORK, KMS_CONCEPT, KMS_INSTITUTION, KMS_DOSSIER, KMS_EVENT, KMS_ENTITY

from .steps.base import axiom_parts, axioms, is_relation_type, kms_relations

_LABEL_OK = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")

_NODE_KINDS = frozendict({
    KMS_WORK: "Work",
    KMS_CONCEPT: "Concept",
    KMS_INSTITUTION: "Institution",
    KMS_DOSSIER: "Dossier",
    KMS_EVENT: "Event",
    KMS_ENTITY: "Entity"
})


@dataclass
class NodeRow:
    """
    One node of the property graph.

    Attributes:
        uri (str): URI of the resource.
        kind (str): Node kind: Work / Concept / Institution / Dossier / Event / Entity.
        labels (tuple[str, ...]): Extra labels besides Resource and the kind, e.g. ``("Regulation",)``.
        props (dict[str, Any]): Node properties.
        alias (list[str]): Alias URIs of the resource.
        stub (bool): Whether the node is only a placeholder for a work known just by reference.
    """
    uri: str
    kind: str  # Work / Concept / Institution / Entity
    labels: tuple[str, ...]  # extra labels besides Resource and the kind, e.g. ("Regulation",)
    props: dict[str, Any] = field(default_factory=dict)
    alias: list[str] = field(default_factory=list)
    stub: bool = False


@dataclass
class RelRow:
    """
    One relationship of the property graph.

    Attributes:
        start (str): URI of the start node.
        type (str): Relationship type.
        end (str): URI of the end node.
        locator (str): Locator that distinguishes parallel edges; empty if the edge is not annotated.
        props (dict[str, Any]): Relationship properties.
    """
    start: str
    type: str
    end: str
    locator: str = ""
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class PropertyGraphBatch:
    """
    The result of one projection.

    Attributes:
        nodes (list[NodeRow]): The projected nodes.
        relationships (list[RelRow]): The projected relationships.
        warnings (list[str]): Problems found while projecting.
    """
    nodes: list[NodeRow] = field(default_factory=list)
    relationships: list[RelRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def nodes_by_kind(self) -> Counter:
        """
        Count the nodes per kind, stub works separately as ``Work (stub)``.

        Returns:
            Counter: Number of nodes per kind.
        """
        return Counter(("Work (stub)" if n.stub else n.kind) for n in self.nodes)

    def relationships_by_type(self) -> Counter:
        """
        Count the relationships per type.

        Returns:
            Counter: Number of relationships per type.
        """
        return Counter(r.type for r in self.relationships)


def doc_type_label(
    doc_type: str
) -> Optional[str]:
    """
    Convert a document type to a Neo4j label, e.g. ``regulation_implementing`` -> ``RegulationImplementing``.

    Args:
        doc_type (str): The document type.

    Returns:
        Optional[str]: The label, or None if the result is not a safe Neo4j label.
    """
    label = "".join(part[:1].upper() + part[1:] for part in re.split(r"[^A-Za-z0-9]+", doc_type) if part)
    return label if _LABEL_OK.match(label) else None


def to_python(
    value: Literal
) -> Any:
    """
    Convert a literal to a value the Neo4j driver can store (bool, int, float, date, datetime, str).

    Args:
        value (Literal): The RDF literal.

    Returns:
        Any: The Python value; the lexical form as ``str`` if the literal cannot be converted.
    """
    dt = value.datatype
    text = str(value)
    try:
        if dt == XSD.boolean:
            return text.strip().lower() in ("true", "1")
        if dt in (XSD.integer, XSD.int, XSD.long, XSD.positiveInteger, XSD.nonNegativeInteger, XSD.gYear):
            return int(text)
        if dt in (XSD.decimal, XSD.double, XSD.float):
            return float(text)
        if dt == XSD.date:
            return date.fromisoformat(text)
        if dt == XSD.dateTime:
            return datetime.fromisoformat(text)
    except ValueError:
        pass
    return text


class GraphProjector:
    """
    Canonical RDF -> :class:`PropertyGraphBatch`.

    Nodes are the resources typed ``kms:Work|Concept|Institution|Entity``; relationships are the ``kms:TYPE`` triples. An edge that has
    relation annotations (``owl:Axiom``) becomes one relationship per distinct locator, otherwise one relationship with an empty locator -
    this is the identity ``(start, type, end, locator)`` used for ``MERGE`` by the loader.
    """

    def project(
        self,
        graph: Graph
    ) -> PropertyGraphBatch:
        """
        Project a canonical graph to property-graph rows.

        Args:
            graph (Graph): The canonical RDF graph.

        Returns:
            PropertyGraphBatch: The nodes, relationships and warnings, sorted for deterministic output.
        """
        batch = PropertyGraphBatch()
        nodes: dict[str, NodeRow] = {}
        for cls, kind in _NODE_KINDS.items():
            for subject in graph.subjects(RDF.type, cls):
                if isinstance(subject, URIRef):
                    nodes[str(subject)] = self._node(graph, subject, kind)

        annotated: dict[tuple[str, str, str], list[RelRow]] = {}
        for ax in axioms(graph):
            src, props, tgt = axiom_parts(graph, ax)
            if src is None or not isinstance(tgt, URIRef) or not props or not is_relation_type(str(props[0])):
                batch.warnings.append("annotation without a valid relation skipped")
                continue
            row = RelRow(str(src), str(props[0])[len(str(KMS)):], str(tgt))
            for p, o in graph.predicate_objects(ax):
                if p == K_LOCATOR:
                    row.locator = str(o)
                elif str(p).startswith(str(KMS)) and isinstance(o, Literal):
                    self._put(row.props, str(p)[len(str(KMS)):], o)
            annotated.setdefault((row.start, row.type, row.end), []).append(row)

        seen: set[tuple[str, str, str, str]] = set()
        for s, p, o in kms_relations(graph):
            edge = (str(s), str(p)[len(str(KMS)):], str(o))
            rows = annotated.get(edge) or [RelRow(*edge)]
            for row in rows:
                key = (row.start, row.type, row.end, row.locator)
                if key in seen:
                    continue
                seen.add(key)
                batch.relationships.append(row)
                for uri in (row.start, row.end):
                    if uri not in nodes:  # defensive: an endpoint the transformer did not type
                        nodes[uri] = NodeRow(uri, "Work", (), {}, [], True)
                        batch.warnings.append(f"endpoint without node kind: {uri}")
        batch.nodes = sorted(nodes.values(), key=lambda n: n.uri)
        batch.relationships.sort(key=lambda r: (r.start, r.type, r.end, r.locator))
        return batch

    def _node(
        self,
        graph: Graph,
        subject: URIRef,
        kind: str
    ) -> NodeRow:
        """
        Build the node row of one resource from its ``kms:`` literal properties.

        Args:
            graph (Graph): The canonical RDF graph.
            subject (URIRef): The resource to project.
            kind (str): The node kind.

        Returns:
            NodeRow: The node row.
        """
        row = NodeRow(str(subject), kind, ())
        for p, o in graph.predicate_objects(subject):
            if not isinstance(o, Literal) or not str(p).startswith(str(KMS)) or is_relation_type(str(p)):
                continue
            name = str(p)[len(str(KMS)):]
            if p == K_ALIAS:
                row.alias.append(str(o))
            elif p == K_STUB:
                row.stub = bool(to_python(o))
            elif p == K_DOC_TYPE:
                row.props["docType"] = str(o)
                label = doc_type_label(str(o))
                if label:
                    row.labels = (label,)
            else:
                self._put(row.props, name, o)
        row.alias.sort()
        return row

    @staticmethod
    def _put(
        props: dict[str, Any],
        name: str,
        value: Literal
    ) -> None:
        """
        Store a literal in ``props``; repeated values of the same name are collected into a list without duplicates.

        Args:
            props (dict[str, Any]): The properties to update.
            name (str): The property name.
            value (Literal): The literal to store.
        """
        python_value = to_python(value)
        if name not in props:
            props[name] = python_value
        elif isinstance(props[name], list):
            if python_value not in props[name]:
                props[name].append(python_value)
        elif props[name] != python_value:
            props[name] = [props[name], python_value]