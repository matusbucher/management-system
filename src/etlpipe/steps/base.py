from __future__ import annotations

from abc import ABC
from typing import Iterator, Optional

from rdflib import BNode, Graph, URIRef, Literal
from rdflib.namespace import OWL, RDF, XSD

from ..constants import KMS
from ..interfaces import Transformer


class TransformStep(Transformer, ABC):
    """
    Interface for transformer steps in transformer chain. Inherits from ``Transformer``.
    """


# placeholder values used by Cellar for "unknown" / "no end"
_SENTINEL_STRINGS = frozenset({"$BUILD_INFO$", "TO_VALIDATE"})
_SENTINEL_DATES = frozenset({"1001-01-01", "9999-12-31"})


def is_sentinel(
    value: Literal
) -> bool:
    """
    Determine if a literal is a Cellar placeholder value ("unknown" / "no end").

    Args:
        value (Literal): The literal to check.

    Returns:
        bool: True if the literal is a placeholder string or a placeholder date, False otherwise.
    """
    text = str(value).strip()
    return text in _SENTINEL_STRINGS or (value.datatype == XSD.date and text in _SENTINEL_DATES)


def axioms(
    graph: Graph
) -> list[BNode]:
    """
    Get all ``owl:Axiom`` nodes (the relation annotations) in the ``graph``.

    Args:
        graph (Graph): The RDF graph to search for axioms.

    Returns:
        list[BNode]: A list of blank nodes representing the axioms.
    """
    return [a for a in graph.subjects(RDF.type, OWL.Axiom) if isinstance(a, BNode)]


def axiom_parts(
    graph: Graph,
    axiom: BNode
) -> tuple[Optional[URIRef], list[URIRef], Optional[object]]:
    """
    Get the parts of an ``owl:Axiom`` node: the annotated source, the annotated properties,
    and the annotated target.

    Args:
        graph (Graph): The RDF graph containing the axiom.
        axiom (BNode): The blank node representing the axiom.

    Returns:
        tuple[Optional[URIRef], list[URIRef], Optional[object]]: A tuple containing the annotatedsource (or None if not a URIRef), a list of annotated properties, and the annotated target.
    """
    source = graph.value(axiom, OWL.annotatedSource)
    target = graph.value(axiom, OWL.annotatedTarget)
    props = [p for p in graph.objects(axiom, OWL.annotatedProperty) if isinstance(p, URIRef)]
    return (source if isinstance(source, URIRef) else None), props, target


def remove_axiom(
    graph: Graph,
    axiom: BNode
) -> None:
    """
    Remove an ``owl:Axiom`` node from the graph.

    Args:
        graph (Graph): The RDF graph containing the axiom.
        axiom (BNode): The blank node representing the axiom.
    """
    graph.remove((axiom, None, None))


def local_name(
    uri: str
) -> str:
    """
    Get the local name of a URI.

    Args:
        uri (str): The URI to extract the local name from.

    Returns:
        str: The local name of the URI.
    """
    return uri.rsplit("#", 1)[-1] if "#" in uri else uri.rsplit("/", 1)[-1]


def uri_nodes(
    graph: Graph
) -> set[URIRef]:
    """
    Get all resource URIs that occur as subject or object (classes of ``rdf:type`` and the properties named by
    ``owl:annotatedProperty`` are vocabulary, not resources).

    Args:
        graph (Graph): The RDF graph to search for resource URIs.

    Returns:
        set[URIRef]: A set of resource URIs found in the graph.
    """
    nodes: set[URIRef] = set()
    for s, p, o in graph:
        if isinstance(s, URIRef):
            nodes.add(s)
        if isinstance(o, URIRef) and p != RDF.type and p != OWL.annotatedProperty:
            nodes.add(o)
    return nodes


def is_relation_type(
    uri: str
) -> bool:
    """
    Determine if a URI represents a relation type in the KMS vocabulary
    (``kms:TYPE`` predicates with an upper case local name).
    
    Args:
        uri (str): The URI to check.

    Returns:
        bool: True if the URI represents a relation type, False otherwise.
    """
    name = uri[len(str(KMS)):] if uri.startswith(str(KMS)) else ""
    return bool(name) and name[0].isupper() and name == name.upper() and name.replace("_", "").isalnum()


def kms_relations(
    graph: Graph
) -> Iterator[tuple[URIRef, URIRef, URIRef]]:
    """
    Relation triples of the canonical vocabulary: (source, kms:TYPE, target).

    Args:
        graph (Graph): The RDF graph to search for relation triples.

    Yields:
        tuple[URIRef, URIRef, URIRef]: Triples representing relations in the canonical vocabulary.
    """
    for s, p, o in graph:
        if isinstance(s, URIRef) and isinstance(p, URIRef) and isinstance(o, URIRef) and is_relation_type(str(p)):
            yield s, p, o