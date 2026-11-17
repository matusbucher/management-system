from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from ..constants import K_CELEX, K_SOURCE_KIND, KMS, KMS_WORK
from ..context import TransformContext
from ..uris import celex_source_kind
from .base import axiom_parts, axioms, TransformStep


_CITES = KMS.CITES


class ScopeFilter(TransformStep):
    """
    Tag every work with ``kms:sourceKind`` and optionally drop citations by the kind of their source work.

    * the source kind comes from the CELEX sector (legislation, preparatory, case-law, national-measure ...);
    * if ``options.citation_source_kinds`` is set, ``CITES`` edges whose source work is of another kind are dropped.

    72 % of the citation edges in the sample documents come from preparatory acts, so this is a policy switch, off by default.
    """
    name = "scope_filter"

    def transform(
        self,
        graph: Graph,
        ctx: TransformContext
    ) -> Graph:
        st = ctx.stats
        kinds: dict[URIRef, str] = {}
        for work in graph.subjects(RDF.type, KMS_WORK):
            if not isinstance(work, URIRef):
                continue
            celex = graph.value(work, K_CELEX)
            kind = celex_source_kind(str(celex) if celex is not None else None)
            kinds[work] = kind
            graph.add((work, K_SOURCE_KIND, Literal(kind)))
            st.tally("source_kinds", kind)

        allowed = ctx.options.citation_source_kinds
        if allowed is None:
            return graph
        removed = 0
        for s, o in list(graph.subject_objects(_CITES)):
            if not isinstance(s, URIRef):  # the kinds are keyed by work URIs
                continue
            kind = kinds.get(s, "unknown")
            if kind not in allowed:
                graph.remove((s, _CITES, o))
                removed += 1
                st.tally("citations_dropped_by_source_kind", kind)
        for ax in axioms(graph):
            src, props, tgt = axiom_parts(graph, ax)
            if props != [_CITES]:
                continue
            kind = kinds.get(src, "unknown") if src is not None else "unknown"  # a headless annotation has no source
            if kind not in allowed:
                graph.remove((ax, None, None))
                st.count("citation_annotations_dropped")
        st.count("citations_dropped", removed)
        return graph
