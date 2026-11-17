from __future__ import annotations

from frozendict import frozendict

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from ..constants import RESOURCE_BASE, KMS, KMS_DOSSIER, KMS_EVENT
from ..context import TransformContext
from ..report import StepReport
from ..uris import classify_uri, dossier_attributes, event_attributes
from .base import TransformStep

_DATE_PROPERTIES = frozenset({"eventDate"})

_DOSSIER_SCHEME_OF_EVENT = frozendict({
    "procedure-event": "procedure",
    "internal_proc-event": "internal_proc",
    "intproc-event": "intproc",
    "case-event": "case"
})


class LifecycleEnricher(TransformStep):
    """
    Give dossier and event nodes the attributes that exist only in their URIs (the dumps carry no literals on them).

    * dossier: ``kms:procedureId`` (``2020_359``), or ``caseId`` / ``sessionId``;
    * event: ``kms:eventDate`` (xsd:date), ``kms:eventCode`` (``PUB_OJ``, ``ADP_PROPLEG``), ``kms:byBody`` (``COM``, ``CONSIL``, ``EP``),
      plus the id of the dossier it belongs to.

    With ``eventDate`` the events of a dossier can be ordered into the lifecycle of the document (proposal, adoption, publication ...).
    Most events are linked only from the documents handled at them, not from their dossier; the ``EVENT_OF`` edge is therefore also derived
    from the event URI (``procedure-event/2020_359.…`` belongs to ``procedure/2020_359``), creating the dossier node when it is not yet there.
    """
    name = "lifecycle_enricher"

    def transform(
        self,
        graph: Graph,
        ctx: TransformContext
    ) -> Graph:
        st = ctx.stats
        for node in sorted({s for s in graph.subjects(RDF.type, KMS_DOSSIER) if isinstance(s, URIRef)}, key=str):
            self._add_attributes(graph, node, dossier_attributes(str(node)), st)
        for node in sorted({s for s in graph.subjects(RDF.type, KMS_EVENT) if isinstance(s, URIRef)}, key=str):
            attrs = event_attributes(str(node))
            self._add_attributes(graph, node, attrs, st)
            if "eventDate" not in attrs:
                st.tally("events_without_date", classify_uri(str(node)).scheme)
            self._link_to_dossier(graph, node, st)
        return graph

    @staticmethod
    def _add_attributes(
        graph: Graph,
        node: URIRef,
        attrs: dict[str, str],
        st: StepReport
    ) -> None:
        """
        Add the given attributes to the specified node in the graph.

        Args:
            graph (Graph): The RDF graph to modify.
            node (URIRef): The node to which attributes will be added.
            attrs (dict[str, str]): A dictionary of attribute names and values.
            st (StepReport): The statistics object for tallying added attributes.
        """
        for key, value in attrs.items():
            literal = Literal(value, datatype=XSD.date) if key in _DATE_PROPERTIES else Literal(value)
            graph.add((node, KMS[key], literal))
            st.tally("attributes_added", key)

    def _link_to_dossier(
        self,
        graph: Graph,
        event: URIRef,
        st: StepReport
    ) -> None:
        """
        Link the given event to its corresponding dossier in the graph.

        Args:
            graph (Graph): The RDF graph to modify.
            event (URIRef): The event node to link.
            st (StepReport): The statistics object for tallying created links.
        """
        info = classify_uri(str(event))
        dossier_scheme = _DOSSIER_SCHEME_OF_EVENT.get(info.scheme)
        head, dot, _ = info.local.partition(".")
        if not dossier_scheme or not dot or not head:
            return
        dossier = URIRef(f"{RESOURCE_BASE}{dossier_scheme}/{head}")
        if (event, KMS.EVENT_OF, dossier) in graph:
            return
        if (dossier, RDF.type, KMS_DOSSIER) not in graph:
            graph.add((dossier, RDF.type, KMS_DOSSIER))
            self._add_attributes(graph, dossier, dossier_attributes(str(dossier)), st)
            st.count("dossiers_created_from_events")
        graph.add((event, KMS.EVENT_OF, dossier))
        st.count("event_of_derived")