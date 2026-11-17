from __future__ import annotations

from collections import defaultdict
from frozendict import frozendict

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL

from ..constants import K_ALIAS, K_CELEX, K_CELLAR_ID, K_ELI, K_OJ_ID, KMS
from ..context import CanonicalScheme, TransformContext
from ..report import StepReport
from ..uris import LEVEL_WORK, classify_uri, identifiers_of, is_structural_cellar, lifecycle_kind
from .base import TransformStep


_IDENTIFIER_PROPERTIES = frozendict({
    "celex": K_CELEX,
    "cellarId": K_CELLAR_ID,
    "eli": K_ELI,
    "ojId": K_OJ_ID
})


class AliasResolver(TransformStep):
    """
    Merge the URIs of one work (``owl:sameAs``) into one canonical URI.

    * the canonical URI is the CELEX URI (or the Cellar UUID URI with ``canonical_scheme=CanonicalScheme.CELLAR``),
      falling back to the other one;
    * every occurrence of an alias - subject, object, relation annotation - is rewritten to the canonical URI;
    * the identifiers (``kms:celex``, ``kms:cellarId``, ``kms:eli``, ``kms:ojId``) and all other aliases
      (``kms:alias``) are stored as properties of the canonical node; ``owl:sameAs`` triples are removed.
    """
    name = "alias_resolver"

    def transform(
        self,
        graph: Graph,
        ctx: TransformContext
    ) -> Graph:
        st = ctx.stats
        parent: dict[URIRef, URIRef] = {}

        def find(
            x: URIRef
        ) -> URIRef:
            """
            Find the union-find root of a URI (with path compression).

            Args:
                x (URIRef): The URI to look up.

            Returns:
                URIRef: The root of the alias group the URI belongs to.
            """
            root = x
            while parent.setdefault(root, root) != root:
                root = parent[root]
            while parent[x] != root:  # path compression
                parent[x], x = root, parent[x]
            return root

        for s, o in graph.subject_objects(OWL.sameAs):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                parent[find(s)] = find(o)

        groups: dict[URIRef, set[URIRef]] = defaultdict(set)
        for node in list(parent):
            groups[find(node)].add(node)

        mapping: dict[URIRef, URIRef] = {}
        canonical_of_group: dict[URIRef, tuple[URIRef, set[URIRef]]] = {}
        for members in groups.values():
            canon = self._choose_canonical(members, ctx.options.canonical_scheme)
            canonical_of_group[canon] = (canon, members)
            st.tally("canonical_by_scheme", classify_uri(str(canon)).scheme)
            if len(members) > 1:
                st.count("alias_groups")
                st.tally("alias_group_size", str(min(len(members), 10)) + ("+" if len(members) >= 10 else ""))
            for m in members:
                if m != canon:
                    mapping[m] = canon
        st.count("uris_merged", len(mapping))

        result = Graph()
        for prefix, ns in graph.namespaces():
            result.bind(prefix, ns)
        result.bind("kms", KMS)
        rewritten = 0
        for s, p, o in graph:
            if p == OWL.sameAs:
                st.count("sameas_removed")
                continue
            s2 = mapping.get(s, s) if isinstance(s, URIRef) else s
            o2 = mapping.get(o, o) if isinstance(o, URIRef) else o
            if s2 is not s or o2 is not o:
                rewritten += 1
            result.add((s2, p, o2))
        st.count("triples_rewritten", rewritten)

        for canon, members in canonical_of_group.values():
            if classify_uri(str(canon)).level != LEVEL_WORK:
                continue
            self._add_identifiers(result, canon, members, st)
        # works that are in no alias group still carry the identifier of their own URI
        grouped = set(parent)
        for node in {s for s in result.subjects() if isinstance(s, URIRef)} - grouped:
            if classify_uri(str(node)).level == LEVEL_WORK:
                self._add_identifiers(result, node, {node}, st)
        return result

    @staticmethod
    def _choose_canonical(
        members: set[URIRef],
        scheme: CanonicalScheme
    ) -> URIRef:
        """
        Canonical URI of an alias group.

        Lifecycle entities (dossiers, events) keep their readable URI (``procedure-event/…``); the Cellar ``<uuid>.NNNN`` alias that
        accompanies them must never win because it looks like an Expression. Works take the CELEX (or Cellar UUID) URI.

        Args:
            members (set[URIRef]): The set of URIs in the alias group.
            scheme (CanonicalScheme): The preferred scheme for canonical URIs.

        Returns:
            URIRef: The chosen canonical URI.
        """
        order = ("celex", "cellar") if scheme == CanonicalScheme.CELEX else ("cellar", "celex")

        def rank(
            uri: URIRef
        ) -> tuple[int, int, int, int, str]:
            """
            Rank a URI for canonical selection.

            Lower tuples are preferred: lifecycle entities first, then non-structural cellar URIs,
            then by scheme, then by URI length, then lexicographically.

            Args:
                uri (URIRef): The URI to rank.

            Returns:
                tuple[int, int, int, int, str]: The sort key of the URI.
            """
            info = classify_uri(str(uri))
            scheme_rank = order.index(info.scheme) if info.scheme in order else len(order)
            rank = (
                0 if lifecycle_kind(str(uri)) else 1,
                1 if is_structural_cellar(str(uri)) else 0,
                scheme_rank,
                len(str(uri)),
                str(uri)
            )
            return rank

        return min(members, key=rank)

    @staticmethod
    def _add_identifiers(
        graph: Graph,
        canon: URIRef,
        members: set[URIRef],
        st: StepReport
    ) -> None:
        """
        One value per identifier kind: the canonical URI's own identifier, else the smallest one;
        the rest stays in ``kms:alias``.

        Args:
            graph (Graph): The RDF graph to add identifiers to.
            canon (URIRef): The canonical URI for the alias group.
            members (set[URIRef]): The set of URIs in the alias group.
            st (StepReport): The step report used to tally added identifiers and conflicts.
        """
        values: dict[str, set[str]] = defaultdict(set)
        for member in members:
            for key, value in identifiers_of(str(member)).items():
                values[key].add(value)
        own = identifiers_of(str(canon))
        for key, found in values.items():
            graph.add((canon, _IDENTIFIER_PROPERTIES[key], Literal(own.get(key) or min(found))))
            st.tally("identifiers_added", key)
            if len(found) > 1:
                st.tally("identifier_conflicts", key)
        for member in sorted(members, key=str):
            if member != canon:
                graph.add((canon, K_ALIAS, Literal(str(member))))