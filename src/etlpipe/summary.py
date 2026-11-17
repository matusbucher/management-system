from __future__ import annotations

from collections import Counter
from typing import Any

from rdflib import Graph
from rdflib.namespace import RDF

from .constants import NODE_CLASSES, KMS, K_DOC_TYPE, K_STUB
from .steps.base import axiom_parts, axioms, kms_relations


def summarize_graph(
    graph: Graph
) -> dict[str, Any]:
    """
    Get the numbers to report after a transformation: nodes by kind, document types, edges by type and annotation
    coverage.

    Args:
        graph (Graph): The canonical work graph.

    Returns:
        dict[str, Any]: The summary statistics (triples, nodes, nodes_by_kind, work_stubs, doc_types, edges,
            edges_by_type, annotated_edges, annotation_axioms, annotation_properties).
    """
    nodes_by_kind: Counter = Counter()
    for cls in NODE_CLASSES:
        n = sum(1 for _ in graph.subjects(RDF.type, cls))
        if n:
            nodes_by_kind[str(cls)[len(str(KMS)):]] = n
    doc_types = Counter(str(o) for o in graph.objects(None, K_DOC_TYPE))
    edges_by_type: Counter = Counter(str(p)[len(str(KMS)):] for _, p, _ in kms_relations(graph))

    annotated: set[tuple] = set()
    annotation_props: Counter = Counter()
    for ax in axioms(graph):
        src, props, tgt = axiom_parts(graph, ax)
        if src is None or tgt is None or not props:
            continue
        annotated.add((src, props[0], tgt))
        for p in graph.predicates(ax, None):
            if str(p).startswith(str(KMS)):
                annotation_props[str(p)[len(str(KMS)):]] += 1
    stub_true = sum(1 for o in graph.objects(None, K_STUB) if str(o).lower() == "true")
    return {
        "triples": len(graph),
        "nodes": sum(nodes_by_kind.values()),
        "nodes_by_kind": dict(nodes_by_kind),
        "work_stubs": stub_true,
        "doc_types": dict(doc_types.most_common()),
        "edges": sum(edges_by_type.values()),
        "edges_by_type": dict(edges_by_type.most_common()),
        "annotated_edges": len(annotated),
        "annotation_axioms": sum(1 for _ in axioms(graph)),
        "annotation_properties": dict(annotation_props.most_common()),
    }