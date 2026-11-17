from __future__ import annotations

from typing import Optional

from rdflib import Graph, Literal
from rdflib.namespace import XSD

from ..constants import KMS
from ..context import TransformContext
from ..policy import Policy, load_policy

from .base import is_sentinel, TransformStep


class AttributeMapper(TransformStep):
    """
    Rename the literal properties of works to ``kms:<name>`` (config/attributes.csv),
    fold generic/specific twins (same name, same value = one triple), drop placeholder
    values and normalise ``xsd:anyURI`` to plain strings.

    Args:
        policy (Optional[Policy]): The policy object containing attribute rules. If None, the default policy is loaded.
    """
    name = "attribute_mapper"

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
        old: list[tuple] = []
        new: set[tuple] = set()
        for s, p, o in graph:
            if not isinstance(o, Literal):
                continue
            local = Policy.cdm_local(str(p))
            if local is None:
                continue
            old.append((s, p, o))
            rule = self.policy.attribute_rule(local)
            if rule is None or not rule.kms:
                st.tally("dropped_attributes", local)
                continue
            if is_sentinel(o):
                st.tally("sentinel_values_dropped", f"{rule.kms}={o}")
                continue
            if o.datatype == XSD.anyURI:
                o = Literal(str(o))
            new.add((s, KMS[rule.kms], o))
        for t in old:
            graph.remove(t)
        for t in new:
            graph.add(t)
            st.tally("attributes_by_name", str(t[1])[len(str(KMS)):])
        st.count("attribute_triples_in", len(old))
        st.count("attribute_triples_out", len(new))
        return graph