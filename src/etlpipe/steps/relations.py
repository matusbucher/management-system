from __future__ import annotations

from typing import Optional

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF

from ..constants import KMS
from ..context import TransformContext, TransformOptions
from ..policy import Policy, RelationRule, load_policy
from ..report import StepReport
from ..transformer import TransformStep
from .base import axiom_parts, axioms


_AXIOM_STRUCTURE = frozenset({RDF.type, OWL.annotatedSource, OWL.annotatedProperty, OWL.annotatedTarget})


class RelationCanonicalizer(TransformStep):
    """
    Turn CDM relations into canonical ``kms:TYPE`` edges.

    * the generic super-property copy and the specific property of one fact collapse into one edge (materialised inference);
    * every relation is expressed in one direction (``amended_by`` becomes ``amends`` with swapped ends, config/relations.csv);
    * the relation annotations (``owl:Axiom``) are rewritten with their relation. Annotations that cannot be attached to a relation are removed:
      *headless* axioms (no annotatedSource/Property/Target), axioms annotating a literal attribute, and axioms of dropped relations.

    Args:
        policy (Optional[Policy]): The policy object containing relation rules. If None, the default policy is loaded.
    """
    name = "relation_canonicalizer"

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
        opts = ctx.options
        edges: set[tuple[URIRef, URIRef, URIRef]] = set()
        relation_triples = 0
        doomed: list[tuple[URIRef, URIRef, URIRef]] = []
        for s, p, o in graph:
            # relations connect resources: blank-node subjects (annotations) and literal objects (attributes) are not relations
            if not (isinstance(s, URIRef) and isinstance(p, URIRef) and isinstance(o, URIRef)):
                continue
            rule = self._rule(p, opts)
            if rule is None:
                continue
            relation_triples += 1
            doomed.append((s, p, o))
            edge, inverted = self._edge(s, rule, o)
            edges.add(edge)
            if inverted:
                st.count("triples_inverted")
        for t in doomed:
            graph.remove(t)
        st.count("relation_triples_in", relation_triples)
        st.count("duplicates_folded", relation_triples - len(edges))

        self._rewrite_axioms(graph, edges, opts, st)

        for s, p, o in edges:
            graph.add((s, p, o))
            st.tally("edges_by_type", str(p)[len(str(KMS)):])
        st.count("edges_out", len(edges))
        return graph

    def _rule(
        self,
        predicate: URIRef,
        opts: TransformOptions
    ) -> Optional[RelationRule]:
        """
        Get the relation rule that applies to a predicate.

        Args:
            predicate (URIRef): The CDM predicate to look up.
            opts (TransformOptions): The transform options (the included relation categories).

        Returns:
            Optional[RelationRule]: The rule, or None when the predicate is not a relation or is excluded.
        """
        local = Policy.cdm_local(str(predicate))
        if local is None:
            return None
        rule = self.policy.relation_rule(local)
        if rule is None or rule.excluded or rule.category not in opts.include_categories:
            return None
        return rule

    @staticmethod
    def _edge(
        s: URIRef,
        rule: RelationRule,
        o: URIRef
    ) -> tuple[tuple[URIRef, URIRef, URIRef], bool]:
        """
        Build the canonical edge of a relation triple (inverted and ordered as the rule requires).

        Args:
            s (URIRef): The subject of the CDM triple.
            rule (RelationRule): The rule of the relation.
            o (URIRef): The object of the CDM triple.

        Returns:
            tuple[tuple[URIRef, URIRef, URIRef], bool]: The edge (source, kms:TYPE, target) and whether its ends were swapped.
        """
        a, b = (o, s) if rule.invert else (s, o)
        if rule.symmetric and str(b) < str(a):
            a, b = b, a
        return (a, KMS[rule.canonical], b), rule.invert

    def _rewrite_axioms(
        self,
        graph: Graph,
        edges: set[tuple[URIRef, URIRef, URIRef]],
        opts: TransformOptions,
        st: StepReport
    ) -> None:
        """
        Rewrite the relation annotations (``owl:Axiom``) to the canonical edges and remove those that cannot be attached.

        Args:
            graph (Graph): The RDF graph to modify.
            edges (set[tuple[URIRef, URIRef, URIRef]]): The canonical edges; extended by the edges that annotations assert.
            opts (TransformOptions): The transform options (the included relation categories).
            st (StepReport): The step report used to count rewritten and removed annotations.
        """
        for ax in axioms(graph):
            src, props, tgt = axiom_parts(graph, ax)
            st.count("axioms_in")
            if src is None or tgt is None or not props:
                graph.remove((ax, None, None))
                st.count("axioms_headless_removed")
                continue
            if isinstance(tgt, Literal) or not isinstance(tgt, URIRef):
                graph.remove((ax, None, None))
                st.count("axioms_on_attributes_removed")
                continue
            results = set()
            for prop in props:
                rule = self._rule(prop, opts)
                if rule is not None:
                    results.add(self._edge(src, rule, tgt)[0])
            payload = [(p, o) for p, o in graph.predicate_objects(ax) if p not in _AXIOM_STRUCTURE]
            graph.remove((ax, None, None))
            if not results:
                st.count("axioms_dropped_with_relation")
                continue
            for edge in sorted(results, key=lambda e: (str(e[0]), str(e[1]), str(e[2]))):
                node = BNode()
                graph.add((node, RDF.type, OWL.Axiom))
                graph.add((node, OWL.annotatedSource, edge[0]))
                graph.add((node, OWL.annotatedProperty, edge[1]))
                graph.add((node, OWL.annotatedTarget, edge[2]))
                for p, o in payload:
                    graph.add((node, p, o))
                edges.add(edge)  # an annotation asserts its relation as well
                st.count("axioms_rewritten")