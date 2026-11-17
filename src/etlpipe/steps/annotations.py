from __future__ import annotations

from collections import defaultdict
from typing import Optional

import re
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF

from ..constants import ANNOT, K_LOCATOR, KMS
from ..context import TransformContext
from ..policy import Policy, load_policy
from .base import axiom_parts, axioms, is_sentinel, TransformStep


_CODE_WITH_URI = re.compile(r"\{([^|{}]+)\|[^{}]*\}")  # "{AR|http://.../fd_370/AR} 32" -> "AR 32"
_STRUCTURE = frozenset({RDF.type, OWL.annotatedSource, OWL.annotatedProperty, OWL.annotatedTarget})


class AnnotationCleaner(TransformStep):
    """
    Reduce the relation annotations to the useful ones.

    * keeps the whitelisted ``annot:*`` values (config/annotations.csv) under ``kms:<name>``
      and drops the rest (language lists, build info ...);
    * turns ``{CODE|vocabulary-URI}`` markers into ``CODE`` and drops placeholder values;
    * computes the *locator* of the annotated edge from its identity-bearing annotations
      (article, paragraph, modified location ...), which lets one pair of works carry several
      annotated edges of the same type;
    * merges annotations with the same (source, type, target, locator) and removes annotations
      that end up empty (the edge itself stays).

    Args:
        policy (Optional[Policy]): The policy object containing annotation rules. If None, the default policy is loaded.
    """
    name = "annotation_cleaner"

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
        merged: dict[tuple, dict[URIRef, set]] = defaultdict(lambda: defaultdict(set))
        for ax in axioms(graph):
            st.count("axioms_in")
            src, props, tgt = axiom_parts(graph, ax)
            payload = [(p, o) for p, o in graph.predicate_objects(ax) if p not in _STRUCTURE]
            graph.remove((ax, None, None))
            if src is None or tgt is None or not props:
                st.count("axioms_headless_removed")
                continue
            kept: dict[URIRef, set] = defaultdict(set)
            identity: list[str] = []
            for p, o in payload:
                local = str(p)[len(str(ANNOT)):] if str(p).startswith(str(ANNOT)) else None
                rule = self.policy.annotations.get(local) if local else None
                if rule is None or not rule.kms:
                    st.tally("annotations_dropped", local or str(p))
                    continue
                if isinstance(o, URIRef):  # e.g. annot:eli_target carries a URI - kept as a string
                    o = Literal(str(o))
                if not isinstance(o, Literal) or is_sentinel(o):
                    st.tally("annotation_values_dropped", f"{rule.kms}")
                    continue
                value = self._clean_annotation_value(o)
                if not str(value):
                    continue
                kept[KMS[rule.kms]].add(value)
                if rule.identity:
                    identity.append(f"{rule.kms}={value}")
                st.tally("annotations_kept", rule.kms)
            if not kept:
                st.count("axioms_empty_removed")
                continue
            key = (src, props[0], tgt, "|".join(sorted(identity)))
            for p, values in kept.items():
                merged[key][p].update(values)

        for (src, prop, tgt, locator), values in merged.items():
            node = BNode()
            graph.add((node, RDF.type, OWL.Axiom))
            graph.add((node, OWL.annotatedSource, src))
            graph.add((node, OWL.annotatedProperty, prop))
            graph.add((node, OWL.annotatedTarget, tgt))
            if locator:
                graph.add((node, K_LOCATOR, Literal(locator)))
            for p, vals in values.items():
                for v in vals:
                    graph.add((node, p, v))
            st.tally("annotated_edges_by_type", str(prop)[len(str(KMS)):])
        st.count("axioms_out", len(merged))
        return graph

    @staticmethod
    def _clean_annotation_value(
        value: Literal
    ) -> Literal:
        """
        Cleans the annotation value by removing any code with URI patterns and stripping whitespace.

        Args:
            value (Literal): The annotation value to clean.

        Returns:
            Literal: The cleaned annotation value.
        """
        text = _CODE_WITH_URI.sub(r"\1", str(value)).strip()
        return Literal(text, datatype=value.datatype) if value.datatype else Literal(text)