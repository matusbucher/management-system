import json
import logging
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

workspace_root = Path(__file__).parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, XSD

from src.etlpipe.constants import WEMILevel, KMS
from src.etlpipe.context import (DEFAULT_CATEGORIES, CanonicalScheme, Category, LoadContext, TransformContext,
                                 TransformOptions)
from src.etlpipe.extractor import FileExtractor
from src.etlpipe.loader import Neo4jLoader
from src.etlpipe.pipeline import EtlPipeline
from src.etlpipe.projector import GraphProjector, doc_type_label
from src.etlpipe.report import aggregate_reports
from src.etlpipe.steps import AliasResolver, WemiLevelFilter
from src.etlpipe.summary import summarize_graph
from src.etlpipe.transformer import TransformerChain
from src.etlpipe.uris import (celex_doc_type, celex_source_kind, classify_uri, event_attributes, identifiers_of,
                              lifecycle_kind)

RES = "http://publications.europa.eu/resource/"
NIS2 = URIRef(RES + "celex/32022L2555")
SWD = URIRef(RES + "comnat/SWD_2023_0697_FIN")
CITED = URIRef(RES + "celex/32008R0300")
AMENDING = URIRef(RES + "oj/L_202401183")

FIXTURE = """
@prefix cdm: <http://publications.europa.eu/ontology/cdm#> .
@prefix annot: <http://publications.europa.eu/ontology/annotation#> .
@prefix cmr: <http://publications.europa.eu/ontology/cdm/cmr#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix res: <http://publications.europa.eu/resource/> .

# one work under four URIs
res:cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1 owl:sameAs res:celex/32022L2555 , res:oj/JOL_2022_333_R_0002 , res:eli/dir/2022/2555/oj ;
    cmr:creationDate "2022-12-27T09:08:10+01:00"^^xsd:dateTime .
# the expression of the work (WEMI level 2)
res:cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1.0006 owl:sameAs res:procedure-event/2022_272_x .
res:oj/JOL_2022_333_R_0002.ENG cdm:expression_title "NIS2 (English)" .

# incoming relations on the CELEX node: specific property + generic twin
res:celex/32022L2555 a cdm:work , cdm:resource_legal ;
    cdm:work_cited_by_work res:comnat/SWD_2023_0697_FIN ;
    cdm:cited_by res:comnat/SWD_2023_0697_FIN ;
    cdm:resource_legal_amended_by_resource_legal res:oj/L_202401183 ;
    cdm:amended_by res:oj/L_202401183 ;
    cdm:resource_legal_in-force true .

# own attributes and outgoing relations on the OJ node
res:oj/JOL_2022_333_R_0002 a cdm:work , cdm:resource_legal , cdm:legislation_secondary , cdm:directive ;
    cdm:work_cites_work res:celex/32008R0300 ;
    cdm:resource_legal_year "2022"^^xsd:gYear ;
    cdm:resource_legal_date_entry-into-force "2023-01-16"^^xsd:date ;
    cdm:date "2023-01-16"^^xsd:date ;
    cdm:resource_legal_date_end-of-validity "9999-12-31"^^xsd:date ;
    cdm:resource_legal_id_celex "32022L2555" ;
    cdm:work_has_expression res:oj/JOL_2022_333_R_0002.ENG ;
    cdm:work_is_about_concept_eurovoc <http://eurovoc.europa.eu/4420> ;
    cdm:work_created_by_agent res:authority/corporate-body/CONSIL ;
    annot:build_info "$BUILD_INFO$" .

res:authority/corporate-body/CONSIL a cdm:institution , skos:Concept .
<http://eurovoc.europa.eu/4420> a skos:Concept ; skos:inScheme <http://eurovoc.europa.eu/100141> .

# a dossier (non-work entity) that contains the work
res:dossier/2020_1 a cdm:dossier ; cdm:dossier_contains_work res:celex/32022L2555 .

# the legislative procedure of NIS2: dossier, one event, the event's Cellar alias (looks like an expression!), event type, proposal
res:procedure/2020_359 a cdm:dossier , cdm:procedure_interinstitutional ; cdm:dossier_contains_event res:procedure-event/2020_359.2022-12-27_PUB_OJ ;
    cdm:contains res:procedure-event/2020_359.2022-12-27_PUB_OJ ; cdm:dossier_contains_work res:comnat/COM_2020_0823_FIN .
res:procedure-event/2020_359.2022-12-27_PUB_OJ a cdm:event , cdm:event_legal ; cdm:event_part_of_dossier res:procedure/2020_359 ;
    cdm:part_of res:procedure/2020_359 .
res:cellar/7e075fd8-34e9-11ed-9c68-01aa75ed71a1.0024 owl:sameAs res:procedure-event/2020_359.2022-12-27_PUB_OJ .
res:celex/32022L2555 cdm:work_part_of_event res:procedure-event/2020_359.2022-12-27_PUB_OJ ; cdm:part_of res:procedure-event/2020_359.2022-12-27_PUB_OJ ;
    cdm:resource_legal_produced_by_dossier res:procedure/2020_359 ; cdm:produced_by res:procedure/2020_359 .
res:authority/event/PUB_OJ cdm:is_type_of res:procedure-event/2020_359.2022-12-27_PUB_OJ .
res:comnat/COM_2020_0823_FIN cdm:initiates res:procedure/2020_359 .

# two annotations of the same amendment (different modified location), one headless annotation
[] a owl:Axiom ; owl:annotatedSource res:celex/32022L2555 ; owl:annotatedProperty cdm:resource_legal_amended_by_resource_legal ;
    owl:annotatedTarget res:oj/L_202401183 ;
    annot:reference_to_modified_location "{AR|http://publications.europa.eu/resource/authority/fd_370/AR} 32" ;
    annot:start_of_validity "2024-05-20" ; annot:role2 "{R|http://publications.europa.eu/resource/authority/fd_375/R}" ;
    annot:language_list "ENG" , "FRA" ; annot:build_info "$BUILD_INFO$" .
[] a owl:Axiom ; owl:annotatedSource res:celex/32022L2555 ; owl:annotatedProperty cdm:resource_legal_amended_by_resource_legal ;
    owl:annotatedTarget res:oj/L_202401183 ;
    annot:reference_to_modified_location "{AR|http://publications.europa.eu/resource/authority/fd_370/AR} 33" ;
    annot:start_of_validity "2024-05-20" .
[] a owl:Axiom ; annot:impact "text" ; annot:start_of_validity "2018-12-11" .
"""


def fixture_graph() -> Graph:
    # Turtle prefixed names cannot contain "/", so `res:celex/32022L2555` is expanded to a full IRI first
    text = re.sub(r"(?<![\w/])res:(\S+)", lambda m: f"<{RES}{m.group(1)}>", FIXTURE)
    g = Graph()
    g.parse(data=text, format="turtle")
    return g


def run_chain(options: Optional[TransformOptions] = None) -> tuple[Graph, TransformContext]:
    ctx = TransformContext(options=options or TransformOptions(), source="fixture")
    return TransformerChain.default_chain().transform(fixture_graph(), ctx), ctx


def edges(graph: Graph, relation: str) -> set[tuple]:
    return {(s, o) for s, _, o in graph.triples((None, KMS[relation], None))}


class FakeDb:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run_write(self, query, parameters=None):
        self.calls.append((query, parameters or {}))
        return {"nodes_created": 1, "relationships_created": 1, "properties_set": 2}


class TestUris(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_uri(RES + "cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1").level, "work")
        self.assertEqual(classify_uri(RES + "cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1.0006").level, "expression")
        self.assertEqual(classify_uri(RES + "cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1.0006.01").level, "manifestation")
        self.assertEqual(classify_uri(RES + "oj/JOL_2022_333_R_0002.ENG").level, "expression")
        self.assertEqual(classify_uri(RES + "authority/corporate-body/EP").level, "institution")
        self.assertEqual(classify_uri("http://eurovoc.europa.eu/4420").level, "concept")

    def test_identifiers_and_kinds(self):
        self.assertEqual(event_attributes(RES + "procedure-event/2025_404.2025-12-17_ADP_PROPLEG_byCOM"),
                         {"procedureId": "2025_404", "eventDate": "2025-12-17", "byBody": "COM", "eventCode": "ADP_PROPLEG"})
        self.assertEqual(event_attributes(RES + "case-event/C-245%2F25.CC_NC_PUB_OJ_2026-01-26"),
                         {"caseId": "C-245/25", "eventDate": "2026-01-26", "eventCode": "CC_NC_PUB_OJ"})
        self.assertEqual(lifecycle_kind(RES + "procedure/2020_359"), "dossier")
        self.assertEqual(lifecycle_kind(RES + "session-sitting/EP_2025-06-16.2025-06-18_3"), "event")
        self.assertEqual(lifecycle_kind(RES + "pegase/123456.2026-01-05_PUB_OJ"), "event")
        self.assertIsNone(lifecycle_kind(RES + "celex/32022L2555"))
        self.assertIsNone(lifecycle_kind(RES + "pegase/123456"))
        self.assertEqual(identifiers_of(RES + "celex/32022R2554R%2803%29"), {"celex": "32022R2554R(03)"})
        self.assertEqual(celex_source_kind("52023SC0697"), "preparatory")
        self.assertEqual(celex_doc_type("32022R2554"), "regulation")
        self.assertIsNone(celex_doc_type("62024CJ0001"))
        self.assertEqual(doc_type_label("regulation_implementing"), "RegulationImplementing")
        self.assertEqual(doc_type_label("opinion_advocate-general"), "OpinionAdvocateGeneral")


class TestSteps(unittest.TestCase):
    def test_alias_resolver_merges_group_and_stores_identifiers(self):
        ctx = TransformContext()
        out = AliasResolver().transform(fixture_graph(), ctx)
        self.assertEqual(len(list(out.triples((None, OWL.sameAs, None)))), 0)
        self.assertEqual(out.value(NIS2, KMS.cellarId), Literal("9b84d482-85bd-11ed-9887-01aa75ed71a1"))
        self.assertEqual(out.value(NIS2, KMS.ojId), Literal("JOL_2022_333_R_0002"))
        self.assertEqual(out.value(NIS2, KMS.eli), Literal("http://data.europa.eu/eli/dir/2022/2555/oj"))
        self.assertEqual(out.value(NIS2, KMS.celex), Literal("32022L2555"))
        self.assertIn((NIS2, KMS.alias, Literal(RES + "oj/JOL_2022_333_R_0002")), out)
        # attributes that were on the OJ alias are now on the canonical node
        self.assertIsNotNone(out.value(NIS2, URIRef("http://publications.europa.eu/ontology/cdm#resource_legal_year")))
        self.assertEqual(ctx.stats.counters["alias_groups"], 3)

    def test_cellar_canonical_scheme(self):
        ctx = TransformContext(options=TransformOptions(canonical_scheme=CanonicalScheme.CELLAR))
        out = AliasResolver().transform(fixture_graph(), ctx)
        canonical = URIRef(RES + "cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1")
        self.assertIn((canonical, KMS.celex, Literal("32022L2555")), out)

    def test_group_with_two_celex_numbers_keeps_a_single_identifier(self):
        g = Graph()
        g.add((URIRef(RES + "celex/32022R2554"), OWL.sameAs, URIRef(RES + "celex/32022R2554R%2803%29")))
        g.add((URIRef(RES + "celex/32022R2554"), OWL.sameAs, URIRef(RES + "oj/L_2022333")))
        ctx = TransformContext()
        out = AliasResolver().transform(g, ctx)
        canonical = URIRef(RES + "celex/32022R2554")
        self.assertEqual(list(out.objects(canonical, KMS.celex)), [Literal("32022R2554")])
        self.assertIn((canonical, KMS.alias, Literal(RES + "celex/32022R2554R%2803%29")), out)
        self.assertEqual(ctx.stats.breakdowns["identifier_conflicts"]["celex"], 1)

    def test_wemi_filter_removes_expressions_only_when_not_allowed(self):
        resolved = AliasResolver().transform(fixture_graph(), TransformContext())
        expression = URIRef(RES + "oj/JOL_2022_333_R_0002.ENG")
        kept = WemiLevelFilter().transform(Graph() + resolved, TransformContext(options=TransformOptions(
            wemi_levels=frozenset({WEMILevel.WORK, WEMILevel.EXPRESSION}))))
        self.assertTrue(any(True for _ in kept.triples((expression, None, None))))
        removed = WemiLevelFilter().transform(Graph() + resolved, TransformContext())
        self.assertFalse(any(True for _ in removed.triples((expression, None, None))))
        self.assertFalse(any(True for _ in removed.triples((None, None, expression))))

    def test_dossier_is_removed_unless_lifecycle_is_enabled(self):
        resolved = AliasResolver().transform(fixture_graph(), TransformContext())
        dossier = URIRef(RES + "dossier/2020_1")
        event = URIRef(RES + "procedure-event/2020_359.2022-12-27_PUB_OJ")
        out = WemiLevelFilter().transform(Graph() + resolved, TransformContext())
        self.assertFalse(any(True for _ in out.triples((dossier, None, None))))
        self.assertFalse(any(True for _ in out.triples((event, None, None))))
        opts = TransformOptions(include_categories=DEFAULT_CATEGORIES | {Category.LIFECYCLE})
        out = WemiLevelFilter().transform(Graph() + resolved, TransformContext(options=opts))
        self.assertTrue(any(True for _ in out.triples((dossier, None, None))))
        self.assertTrue(any(True for _ in out.triples((event, None, None))))  # not mistaken for an expression

    def test_event_keeps_its_readable_uri_not_the_cellar_alias(self):
        out = AliasResolver().transform(fixture_graph(), TransformContext())
        event = URIRef(RES + "procedure-event/2020_359.2022-12-27_PUB_OJ")
        self.assertIn((event, KMS.alias, Literal(RES + "cellar/7e075fd8-34e9-11ed-9c68-01aa75ed71a1.0024")), out)
        self.assertEqual(lifecycle_kind(str(event)), "event")
        self.assertEqual(classify_uri(str(event)).level, "work")


LIFECYCLE = TransformOptions(include_categories=DEFAULT_CATEGORIES | {Category.LIFECYCLE})
PROCEDURE = URIRef(RES + "procedure/2020_359")
EVENT = URIRef(RES + "procedure-event/2020_359.2022-12-27_PUB_OJ")
PROPOSAL = URIRef(RES + "comnat/COM_2020_0823_FIN")
EVENT_TYPE = URIRef(RES + "authority/event/PUB_OJ")


class TestLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, cls.ctx = run_chain(LIFECYCLE)

    def test_nodes_and_attributes(self):
        g = self.graph
        self.assertIn((PROCEDURE, RDF.type, KMS.Dossier), g)
        self.assertIn((EVENT, RDF.type, KMS.Event), g)
        self.assertEqual(g.value(PROCEDURE, KMS.procedureId), Literal("2020_359"))
        self.assertEqual(g.value(PROCEDURE, KMS.docType), Literal("procedure_interinstitutional"))
        self.assertEqual(g.value(EVENT, KMS.eventDate), Literal("2022-12-27", datatype=XSD.date))
        self.assertEqual(g.value(EVENT, KMS.eventCode), Literal("PUB_OJ"))
        self.assertEqual(g.value(EVENT, KMS.procedureId), Literal("2020_359"))
        self.assertEqual(g.value(EVENT, KMS.docType), Literal("event_legal"))

    def test_lifecycle_edges(self):
        g = self.graph
        self.assertEqual(edges(g, "AT_EVENT"), {(NIS2, EVENT)})
        self.assertEqual(edges(g, "EVENT_OF"), {(EVENT, PROCEDURE)})
        self.assertEqual(edges(g, "PRODUCED_BY"), {(NIS2, PROCEDURE)})
        self.assertEqual(edges(g, "INITIATED_BY"), {(PROCEDURE, PROPOSAL)})  # proposal initiates -> dossier INITIATED_BY proposal
        self.assertEqual(edges(g, "HAS_TYPE"), {(EVENT, EVENT_TYPE)})
        self.assertIn((RES + "comnat/COM_2020_0823_FIN", None), {(str(o), None) for _, o in edges(g, "IN_PROCEDURE")} | {(str(s), None) for s, _ in edges(g, "IN_PROCEDURE")})
        self.assertNotIn(KMS.PART_OF, set(g.predicates()))  # the generic membership property is replaced by the specific ones

    def test_event_of_is_derived_from_the_event_uri(self):
        from src.etlpipe.constants import KMS_EVENT
        from src.etlpipe.steps import LifecycleEnricher
        ev = URIRef(RES + "procedure-event/2025_404.2025-12-17_ADP_PROPLEG_byCOM")
        g = Graph()
        g.add((ev, RDF.type, KMS_EVENT))
        ctx = TransformContext()
        LifecycleEnricher().transform(g, ctx)
        dossier = URIRef(RES + "procedure/2025_404")
        self.assertIn((ev, KMS.EVENT_OF, dossier), g)
        self.assertIn((dossier, RDF.type, KMS.Dossier), g)
        self.assertEqual(g.value(dossier, KMS.procedureId), Literal("2025_404"))
        self.assertEqual(ctx.stats.counters["event_of_derived"], 1)

    def test_off_by_default(self):
        g, _ = run_chain()
        self.assertFalse(any(True for _ in g.triples((PROCEDURE, None, None))))
        self.assertFalse(any(True for _ in g.triples((EVENT, None, None))))
        self.assertEqual(edges(g, "AT_EVENT"), set())

    def test_projection_and_loader_labels(self):
        batch = GraphProjector().project(self.graph)
        nodes = {n.uri: n for n in batch.nodes}
        self.assertEqual(nodes[str(EVENT)].kind, "Event")
        self.assertEqual(nodes[str(EVENT)].props["eventDate"].isoformat(), "2022-12-27")
        self.assertEqual(nodes[str(PROCEDURE)].labels, ("ProcedureInterinstitutional",))
        self.assertEqual(batch.warnings, [])
        db = FakeDb()
        Neo4jLoader(db).load(self.graph, LoadContext(source="fixture"))
        queries = " ".join(q for q, _ in db.calls)
        self.assertIn("SET n:Event", queries)
        self.assertIn("SET n:Dossier", queries)
        self.assertIn("FOR (e:Event) ON (e.eventDate)", queries)

    def test_statistics(self):
        steps = {s.name: s for s in self.ctx.report.steps}
        self.assertEqual(steps["lifecycle_enricher"].breakdowns["attributes_added"]["eventDate"], 1)
        self.assertEqual(steps["type_reducer"].breakdowns["node_kinds"]["Event"], 2)  # the PUB_OJ event and the dateless 2022_272_x one
        self.assertEqual(steps["lifecycle_enricher"].breakdowns["events_without_date"]["procedure-event"], 1)
        self.assertEqual(steps["relation_canonicalizer"].breakdowns["edges_by_type"]["AT_EVENT"], 1)
        summary = summarize_graph(self.graph)
        self.assertEqual(summary["nodes_by_kind"]["Dossier"], 2)  # procedure/2020_359 and dossier/2020_1
        self.assertEqual(summary["nodes_by_kind"]["Event"], 2)


class TestChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, cls.ctx = run_chain()

    def test_output_is_clean(self):
        g = self.graph
        self.assertEqual(len(list(g.triples((None, OWL.sameAs, None)))), 0)
        self.assertFalse({p for p in g.predicates() if "ontology/cdm" in str(p) or "ontology/annotation" in str(p)})
        self.assertFalse(any(True for _ in g.triples((URIRef(RES + "oj/JOL_2022_333_R_0002.ENG"), None, None))))
        self.assertFalse(any(True for _ in g.triples((URIRef(RES + "dossier/2020_1"), None, None))))

    def test_relations_are_folded_and_in_one_direction(self):
        g = self.graph
        self.assertEqual(edges(g, "CITES"), {(SWD, NIS2), (NIS2, CITED)})
        self.assertEqual(edges(g, "AMENDS"), {(AMENDING, NIS2)})  # amended_by -> amends with swapped ends

    def test_work_node_properties(self):
        g = self.graph
        self.assertEqual(g.value(NIS2, KMS.docType), Literal("directive"))
        self.assertEqual(g.value(NIS2, KMS.stub), Literal(False, datatype=XSD.boolean))
        self.assertEqual(g.value(NIS2, KMS.year), Literal("2022", datatype=XSD.gYear))
        self.assertEqual(g.value(NIS2, KMS.dateEntryIntoForce), Literal("2023-01-16", datatype=XSD.date))
        self.assertIsNone(g.value(NIS2, KMS.dateEndOfValidity))  # 9999-12-31 is a placeholder
        self.assertEqual(g.value(NIS2, KMS.inForce), Literal(True))
        self.assertEqual(g.value(NIS2, KMS.sourceKind), Literal("legislation"))
        self.assertEqual(g.value(SWD, KMS.stub), Literal(True, datatype=XSD.boolean))

    def test_reference_nodes(self):
        g = self.graph
        concept = URIRef("http://eurovoc.europa.eu/4420")
        institution = URIRef(RES + "authority/corporate-body/CONSIL")
        self.assertIn((NIS2, KMS.IS_ABOUT, concept), g)
        self.assertIn((concept, RDF.type, KMS.Concept), g)
        self.assertEqual(g.value(concept, KMS.scheme), Literal("eurovoc"))
        self.assertIn((NIS2, KMS.CREATED_BY, institution), g)
        self.assertEqual(g.value(institution, KMS.code), Literal("CONSIL"))

    def test_annotations_become_distinct_edge_instances(self):
        rows = [r for r in GraphProjector().project(self.graph).relationships if r.type == "AMENDS"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({r.props["modifiedLocation"] for r in rows}, {"AR 32", "AR 33"})  # {CODE|URI} markers cleaned
        first = next(r for r in rows if r.props["modifiedLocation"] == "AR 32")
        self.assertEqual(first.props["role"], "R")
        self.assertEqual(first.locator, "modifiedLocation=AR 32|startOfValidity=2024-05-20")
        self.assertNotIn("languageList", first.props)

    def test_report_statistics(self):
        steps = {s.name: s for s in self.ctx.report.steps}
        self.assertEqual(list(steps), [s.name for s in TransformerChain.default_chain().steps])
        self.assertEqual(steps["alias_resolver"].counters["alias_groups"], 3)
        # an expression node that carries only owl:sameAs has no triple left once the aliases are resolved, so only the .ENG node is seen
        self.assertEqual(steps["wemi_filter"].breakdowns["nodes_removed_by_level"]["expression"], 1)
        self.assertEqual(steps["wemi_filter"].breakdowns["nodes_removed_by_level"]["dossier"], 2)
        self.assertEqual(steps["wemi_filter"].breakdowns["nodes_removed_by_level"]["event"], 2)
        self.assertEqual(steps["relation_canonicalizer"].counters["axioms_headless_removed"], 1)
        self.assertGreater(steps["relation_canonicalizer"].counters["duplicates_folded"], 0)
        self.assertEqual(steps["annotation_cleaner"].breakdowns["annotations_dropped"]["language_list"], 2)  # counted per value (ENG, FRA)
        self.assertEqual(steps["attribute_mapper"].breakdowns["sentinel_values_dropped"]["dateEndOfValidity=9999-12-31"], 1)
        self.assertEqual(steps["predicate_filter"].breakdowns["dropped_by_reason"]["system_metadata"], 1)

    def test_context_category_alone_does_not_load_lifecycle_entities(self):
        g, _ = run_chain(TransformOptions(include_categories=DEFAULT_CATEGORIES | {Category.CONTEXT}))
        self.assertFalse(any(True for _ in g.triples((URIRef(RES + "dossier/2020_1"), None, None))))

    def test_citation_scope_filter(self):
        g, ctx = run_chain(TransformOptions(citation_source_kinds=frozenset({"legislation"})))
        self.assertEqual(edges(g, "CITES"), {(NIS2, CITED)})  # the SWD (preparatory act / unknown kind) citation is dropped
        self.assertEqual(ctx.report.step("scope_filter").counters["citations_dropped"], 1)


class TestProjectorAndLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph, _ = run_chain()

    def test_projection(self):
        batch = GraphProjector().project(self.graph)
        nodes = {n.uri: n for n in batch.nodes}
        nis2 = nodes[str(NIS2)]
        self.assertEqual((nis2.kind, nis2.labels, nis2.stub), ("Work", ("Directive",), False))
        self.assertEqual(nis2.props["year"], 2022)  # gYear -> int
        self.assertEqual(nis2.props["inForce"], True)
        self.assertEqual(len(nis2.alias), 3)
        self.assertTrue(nodes[str(SWD)].stub)
        self.assertEqual(nodes["http://eurovoc.europa.eu/4420"].kind, "Concept")
        self.assertEqual(batch.relationships_by_type()["CITES"], 2)
        self.assertEqual(batch.warnings, [])
        keys = {(r.start, r.type, r.end, r.locator) for r in batch.relationships}
        self.assertEqual(len(keys), len(batch.relationships))  # identity is unique

    def test_loader_writes_nodes_before_relationships_in_batches(self):
        db = FakeDb()
        report = Neo4jLoader(db, batch_size=2).load(self.graph, LoadContext(source="fixture"))
        queries = [q for q, _ in db.calls]
        self.assertTrue(queries[0].startswith("CREATE CONSTRAINT"))
        first_rel = next(i for i, q in enumerate(queries) if "MERGE (a)-[r:" in q)
        last_node = max(i for i, q in enumerate(queries) if "MERGE (n:Resource" in q)
        self.assertLess(last_node, first_rel)
        self.assertTrue(any("MERGE (a)-[r:`AMENDS` {locator: row.locator}]->(b)" in q for q in queries))
        for _, params in db.calls:
            self.assertLessEqual(len(params.get("rows", [])), 2)
        self.assertEqual(report.nodes_projected, len(GraphProjector().project(self.graph).nodes))
        self.assertEqual(report.db_counters["nodes_created"], report.batches)
        node_params = [p for q, p in db.calls if "MERGE (n:Resource" in q]
        self.assertTrue(all(p["source"] == "fixture" for p in node_params))

    def test_stub_works_do_not_overwrite_full_nodes(self):
        stub = Neo4jLoader.node_statement("Work", (), True)
        full = Neo4jLoader.node_statement("Work", ("Directive",), False)
        self.assertIn("ON CREATE SET n.stub = true", stub)
        self.assertNotIn("n.stub = false", stub)
        self.assertIn("n.stub = false", full)
        self.assertIn("SET n:Work:Directive", full)

    def test_dry_run_touches_no_database(self):
        db = FakeDb()
        report = Neo4jLoader(db).load(self.graph, LoadContext(dry_run=True))
        self.assertEqual(db.calls, [])
        self.assertTrue(report.dry_run)
        self.assertGreater(report.relationships_projected, 0)


class TestPipelineReporting(unittest.TestCase):
    class InMemoryExtractor:
        def extract(self, source):
            return fixture_graph()

    def test_pipeline_report_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = EtlPipeline(self.InMemoryExtractor(), loader=Neo4jLoader(None), report_dir=Path(tmp))
            reports = pipeline.run_many(["a", "b"], dry_run=True)
            pipeline.write_aggregate(reports)
            first = reports[0]
            self.assertIsNone(first.error)
            self.assertEqual(first.extract.triples, len(fixture_graph()))
            self.assertEqual(first.graph["nodes_by_kind"]["Work"], 4)
            self.assertEqual(first.graph["edges_by_type"]["CITES"], 2)
            self.assertTrue(first.load.dry_run)
            saved = json.loads((Path(tmp) / "a.json").read_text(encoding="utf-8"))
            self.assertEqual([s["name"] for s in saved["transform"]["steps"]], [s.name for s in TransformerChain.default_chain().steps])
            self.assertEqual(len((Path(tmp) / "runs.jsonl").read_text(encoding="utf-8").splitlines()), 2)
            aggregate = json.loads((Path(tmp) / "aggregate.json").read_text(encoding="utf-8"))
            self.assertEqual(aggregate["documents"], 2)
            self.assertEqual(aggregate["steps"]["alias_resolver"]["counters"]["alias_groups"], 6)
            self.assertIn("alias_resolver", first.summary_text())

    def test_failures_are_reported_not_raised(self):
        class Broken:
            def extract(self, source):
                raise RuntimeError("boom")

        report = EtlPipeline(Broken()).run("x")
        self.assertEqual(report.error, "RuntimeError: boom")
        self.assertEqual(aggregate_reports([report])["failed"], ["x"])

    def test_every_step_is_logged(self):
        with self.assertLogs("etlpipe.transform", level=logging.INFO) as logs:
            run_chain()
        text = "\n".join(logs.output)
        for step in TransformerChain.default_chain().steps:
            self.assertIn(step.name, text)

    def test_chains_can_be_nested(self):
        nested = TransformerChain([TransformerChain(TransformerChain.default_chain().steps[:2]), TransformerChain(TransformerChain.default_chain().steps[2:])])
        ctx = TransformContext(source="nested")
        out = nested.transform(fixture_graph(), ctx)
        self.assertIn((SWD, KMS.CITES, NIS2), out)


class TestRealData(unittest.TestCase):
    DORA = workspace_root / "data" / "DORA.rdf"

    @unittest.skipUnless(DORA.exists(), "data/DORA.rdf not available")
    def test_dora_invariants(self):
        graph = FileExtractor().extract(self.DORA)
        ctx = TransformContext(source="DORA")
        out = TransformerChain.default_chain().transform(graph, ctx)
        summary = summarize_graph(out)
        self.assertFalse({p for p in out.predicates() if "ontology/cdm" in str(p)})
        self.assertEqual(len(list(out.triples((None, OWL.sameAs, None)))), 0)
        focal = URIRef(RES + "celex/32022R2554")
        self.assertEqual(out.value(focal, KMS.docType), Literal("regulation"))
        self.assertGreater(summary["edges"], 3000)
        self.assertEqual(summary["nodes_by_kind"].get("Entity", 0), 0)
        batch = GraphProjector().project(out)
        self.assertEqual(batch.warnings, [])
        self.assertEqual(len({(r.start, r.type, r.end, r.locator) for r in batch.relationships}), len(batch.relationships))


if __name__ == "__main__":
    unittest.main()
