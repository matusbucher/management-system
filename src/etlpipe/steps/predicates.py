from __future__ import annotations

from typing import Optional

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF
from rdflib.term import Node

from ..constants import ANNOT, CMR, KMS, SKOS
from ..context import TransformContext, TransformOptions
from ..policy import Policy, load_policy
from ..transformer import TransformStep


class PredicateFilter(TransformStep):
    """
    Drop triples that the policy tables do not keep: unmapped or excluded relations and attributes, relation categories that are not
    enabled, Cellar system metadata, annotations placed directly on resources, SKOS scheme links and foreign vocabularies.

    Triples of blank nodes (relation annotations) are left alone - they are handled when their relation is canonicalised.

    Args:
        policy (Optional[Policy]): The policy object to use for filtering predicates. If None, the default policy is loaded.
    """
    name = "predicate_filter"

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
        doomed: list[tuple] = []
        for s, p, o in graph:
            if isinstance(s, BNode):
                continue
            reason = self._reason(p, o, opts)
            if reason is None:
                st.count("kept")
                continue
            code, detail = reason
            st.tally("dropped_by_reason", code)
            st.tally(f"dropped_{code}", detail)
            doomed.append((s, p, o))
        for t in doomed:
            graph.remove(t)
        st.count("dropped", len(doomed))
        return graph

    def _reason(
        self,
        p: Node,
        o: Node,
        opts: TransformOptions
    ) -> Optional[tuple[str, str]]:
        """
        Decide whether a triple has to be dropped, judging by its predicate and object.

        The predicate is kept when it is ``rdf:type``, ``owl:sameAs`` or already in the ``kms:`` vocabulary. Otherwise it is looked up in
        the policy tables: literal-valued predicates need a mapped attribute, resource-valued ones a mapped relation whose category is enabled.

        Args:
            p (Node): The predicate of the triple.
            o (Node): The object of the triple; decides whether the predicate is treated as an attribute (literal) or a relation (URI).
            opts (TransformOptions): The options of the transformer chain (enabled relation categories, system metadata switch).

        Returns:
            Optional[tuple[str, str]]: ``(reason code, detail)`` if the triple has to be dropped, None if it is kept.
        """
        ps = str(p)
        if p == RDF.type or p == OWL.sameAs or ps.startswith(str(KMS)):
            return None
        if ps.startswith(str(CMR)):
            return None if opts.keep_system_metadata else ("system_metadata", ps.rsplit("#", 1)[-1])
        if ps.startswith(str(ANNOT)):
            return "annotation_on_resource", ps.rsplit("#", 1)[-1]
        if ps.startswith(str(SKOS)):
            return "vocabulary_scheme", ps.rsplit("#", 1)[-1]
        local = Policy.cdm_local(ps)
        if local is None:
            return "foreign_namespace", ps
        if isinstance(o, Literal):
            rule = self.policy.attribute_rule(local)
            if rule is None:
                return "unmapped_attribute", local
            return None if rule.kms else ("excluded_attribute", local)
        if isinstance(o, URIRef):
            rule = self.policy.relation_rule(local)
            if rule is None:
                return "unmapped_relation", local
            if rule.excluded:
                return "excluded_relation", local
            if rule.category not in opts.include_categories:
                return "category_disabled", f"{rule.category.value}:{local}"
            return None
        return "blank_node_object", local