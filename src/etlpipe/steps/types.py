from __future__ import annotations

from collections import defaultdict
from typing import Optional

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from ..constants import (K_CELEX, K_CODE, K_DOC_TYPE, K_SCHEME, K_STUB, KMS_CONCEPT, KMS_DOSSIER, KMS_ENTITY, KMS_EVENT,
                          KMS_INSTITUTION, KMS_WORK, NODE_CLASSES)
from ..context import TransformContext
from ..policy import Policy, load_policy
from ..transformer import TransformStep
from ..uris import LEVEL_CONCEPT, LEVEL_INSTITUTION, celex_doc_type, classify_uri, lifecycle_kind
from .base import uri_nodes


class TypeReducer(TransformStep):
    """
    Replace the CDM class chains by one document type and give every node a kind.

    * ``kms:docType``: the deepest CDM class that is not a technical super-class (``regulation``, ``directive``, ``judgement`` ...);
    * node kind (``rdf:type``): ``kms:Work``, ``kms:Concept`` (+ ``kms:scheme``), ``kms:Institution`` (+ ``kms:code``) or ``kms:Entity``
      (non-work CDM entities such as dossiers, only present when context relations are enabled);
    * ``kms:stub``: true for works that are known only as the end of a relation (no document type).

    Args:
        policy (Optional[Policy]): The policy object containing the CDM class hierarchy. If None, the default policy is loaded.
    """
    name = "type_reducer"

    def __init__(
        self,
        policy: Optional[Policy] = None
    ):
        self.policy = policy or load_policy()

    def transform(
        self,
        graph: Graph,
        ctx: TransformContext
    ) -> Graph:
        st = ctx.stats
        types: dict[URIRef, set[str]] = defaultdict(set)
        removed = 0
        for s, o in list(graph.subject_objects(RDF.type)):
            if isinstance(s, URIRef) and o not in NODE_CLASSES:
                local = Policy.cdm_local(str(o))
                if local:
                    types[s].add(local)
                graph.remove((s, RDF.type, o))
                removed += 1
        st.count("type_triples_removed", removed)

        for node in sorted(uri_nodes(graph), key=str):
            info = classify_uri(str(node))
            classes = types.get(node, set())
            if info.level == LEVEL_CONCEPT:
                graph.add((node, RDF.type, KMS_CONCEPT))
                graph.add((node, K_SCHEME, Literal(info.local.split("/", 1)[0] if info.scheme == "authority" else info.scheme)))
                st.tally("node_kinds", "Concept")
            elif info.level == LEVEL_INSTITUTION:
                graph.add((node, RDF.type, KMS_INSTITUTION))
                graph.add((node, K_CODE, Literal(info.local.rsplit("/", 1)[-1])))
                st.tally("node_kinds", "Institution")
            elif lifecycle_kind(str(node)):
                kind = lifecycle_kind(str(node))
                graph.add((node, RDF.type, KMS_DOSSIER if kind == "dossier" else KMS_EVENT))
                doc_type = self._doc_type(classes)
                if doc_type:
                    graph.add((node, K_DOC_TYPE, Literal(doc_type)))
                    st.tally("doc_types", doc_type)
                st.tally("node_kinds", "Dossier" if kind == "dossier" else "Event")
            else:
                doc_type = self._doc_type(classes)
                if doc_type is None:
                    doc_type = celex_doc_type(self._celex(graph, node))
                    if doc_type:
                        st.count("doc_type_from_celex")
                work_like = not classes or any("work" in self.policy.class_levels(c) for c in classes)
                if not work_like:
                    graph.add((node, RDF.type, KMS_ENTITY))
                    st.tally("node_kinds", "Entity")
                    if doc_type:
                        graph.add((node, K_DOC_TYPE, Literal(doc_type)))
                    continue
                graph.add((node, RDF.type, KMS_WORK))
                is_stub = not classes and doc_type is None
                graph.add((node, K_STUB, Literal(is_stub, datatype=XSD.boolean)))
                if doc_type:
                    graph.add((node, K_DOC_TYPE, Literal(doc_type)))
                    st.tally("doc_types", doc_type)
                st.tally("node_kinds", "Work (stub)" if is_stub else "Work")
        return graph

    @staticmethod
    def _celex(
        graph: Graph,
        node: URIRef
    ) -> Optional[str]:
        """
        Get the CELEX number of a node.

        Args:
            graph (Graph): The RDF graph to search.
            node (URIRef): The node whose ``kms:celex`` is wanted.

        Returns:
            Optional[str]: The CELEX number, or None when the node has none.
        """
        value = graph.value(node, K_CELEX)
        return str(value) if value is not None else None

    def _doc_type(
        self,
        classes: set[str]
    ) -> Optional[str]:
        """
        Get the document type: the deepest CDM class that is not a technical super-class.

        Args:
            classes (set[str]): The local names of the CDM classes of a node.

        Returns:
            Optional[str]: The document type, or None when no class qualifies.
        """
        candidates = [c for c in classes if c in self.policy.classes and c not in self.policy.technical_types]
        if not candidates:
            return None
        return max(candidates, key=lambda c: (self.policy.classes[c].depth, c))