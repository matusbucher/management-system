from __future__ import annotations

from collections import defaultdict
from typing import Optional

from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from ..context import Category, TransformContext
from ..policy import WEMI_LEVELS, Policy, load_policy
from ..transformer import TransformStep
from ..uris import LEVEL_ITEM, LEVEL_EXPRESSION, LEVEL_MANIFESTATION, classify_uri, lifecycle_kind
from .base import axioms, axiom_parts, uri_nodes

LEVEL_ENTITY = "entity"  # CDM entity that is not a WEMI resource: agent, period ...
LEVEL_DOSSIER = "dossier"  # legislative procedure / case / session
LEVEL_EVENT = "event"  # step of a dossier (adoption, publication, opinion, sitting ...)
_STRUCTURAL_LEVELS = frozenset({LEVEL_EXPRESSION, LEVEL_MANIFESTATION, LEVEL_ITEM})


class WemiLevelFilter(TransformStep):
    """
    Remove the nodes that are not wanted.

    * WEMI levels outside ``options.wemi_levels`` (default: Work only);
    * non-work CDM entities (agents, periods ...) unless the ``context`` relation category is enabled;
    * dossiers and their events unless the ``lifecycle`` relation category is enabled.

    The level of a node is decided from, in this order: the structure of its URI, its ``rdf:type`` classes and the declared domains of the
    properties it uses. Every triple that has a removed node as subject or object is dropped, together with the relation annotations
    that refer to it.

    Args:
        policy (Optional[Policy]): The policy object containing the class and property levels. If None, the default policy is loaded.
    """
    name = "wemi_filter"

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
        allowed = {lvl.value for lvl in ctx.options.wemi_levels}
        keep_entities = Category.CONTEXT in ctx.options.include_categories
        keep_lifecycle = Category.LIFECYCLE in ctx.options.include_categories

        types: dict[URIRef, set[str]] = defaultdict(set)
        typed: set[URIRef] = set()
        pred_levels: dict[URIRef, set[str]] = defaultdict(set)
        for s, p, o in graph:
            if not isinstance(s, URIRef):
                continue
            if p == RDF.type:
                local = Policy.cdm_local(str(o))
                if local:
                    typed.add(s)
                    types[s].update(self.policy.class_levels(local))
            else:
                local = Policy.cdm_local(str(p))
                if local:
                    pred_levels[s].update(self.policy.property_levels(local))

        nodes = uri_nodes(graph)
        removed: set[URIRef] = set()
        for node in nodes:
            level, evidence = self._level(node, node in typed, types.get(node, set()), pred_levels.get(node, set()))
            st.tally("node_levels", level)
            st.tally("level_evidence", f"{level}:{evidence}")
            if ((level in WEMI_LEVELS and level not in allowed) or (level == LEVEL_ENTITY and not keep_entities)
                    or (level in (LEVEL_DOSSIER, LEVEL_EVENT) and not keep_lifecycle)):
                removed.add(node)
                st.tally("nodes_removed_by_level", level)
        st.count("nodes_removed", len(removed))

        for ax in axioms(graph):
            src, _props, tgt = axiom_parts(graph, ax)
            if src in removed or tgt in removed:
                graph.remove((ax, None, None))
                st.count("axioms_removed")

        before = len(graph)
        for node in removed:
            graph.remove((node, None, None))
            graph.remove((None, None, node))
        st.count("triples_removed", before - len(graph))
        return graph

    def _level(
        self,
        node: URIRef,
        is_typed: bool,
        type_levels: set[str],
        predicate_levels: set[str]
    ) -> tuple[str, str]:
        """
        Decide the level of a node and the evidence the decision is based on.

        Args:
            node (URIRef): The node to classify.
            is_typed (bool): Whether the node has a CDM ``rdf:type``.
            type_levels (set[str]): The WEMI levels implied by the CDM classes of the node.
            predicate_levels (set[str]): The WEMI levels implied by the domains of the properties the node uses.

        Returns:
            tuple[str, str]: The level and the evidence (``uri``, ``rdf:type``, ``predicate-domain`` or ``none``).
        """
        info = classify_uri(str(node))
        if info.level in _STRUCTURAL_LEVELS:
            return info.level, "uri"
        wemi_from_types = [lvl for lvl in WEMI_LEVELS if lvl in type_levels]
        if wemi_from_types:
            return wemi_from_types[0], "rdf:type"
        if info.level in ("concept", "institution"):
            return info.level, "uri"
        lifecycle = lifecycle_kind(str(node))
        if lifecycle:  # dossier / event: recognised by URI scheme, whether or not the dump types them
            return (LEVEL_DOSSIER if lifecycle == "dossier" else LEVEL_EVENT), "uri"
        if is_typed:  # CDM classes, none of them a WEMI class: dossier, procedure, event, agent ...
            return LEVEL_ENTITY, "rdf:type"
        wemi_from_predicates = [lvl for lvl in WEMI_LEVELS if lvl in predicate_levels]
        if "work" in wemi_from_predicates:
            return "work", "predicate-domain"
        if wemi_from_predicates:
            return wemi_from_predicates[0], "predicate-domain"
        return ("work", "uri") if info.level == "work" else ("other", "none")