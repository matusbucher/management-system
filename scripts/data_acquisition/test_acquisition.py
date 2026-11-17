import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Callable

workspace_root = Path(__file__).resolve().parents[2]
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from scripts.data_acquisition.config import ADJACENT_DESCRIPTORS, CORE_DESCRIPTORS, SEED_CELEX, is_main_act
from scripts.data_acquisition.gatherer import STAGE_EXPANSION, STAGE_SEED, STAGE_TOPIC, WorkIdGatherer, _CHUNK_SIZE, _work_ids_of
from scripts.data_acquisition.work_ids import write_work_ids
from src.etlpipe.work_ids import read_work_ids
from src.eurlex.cellar_api import CellarAPI, CellarPS, CellarResourceId
from src.eurlex.sparql_api import SparqlAPI

RATE_LIMIT_DELAY = 1

CELLAR = "http://publications.europa.eu/resource/cellar/"
EUROVOC = "http://eurovoc.europa.eu/"
NIS2_CELEX = "32022L2555"
NIS2_WORK = "9b84d482-85bd-11ed-9887-01aa75ed71a1"
CRA_CELEX = "32024R2847"

NOTICE = """<?xml version="1.0" encoding="UTF-8"?>
<NOTICE type="identifier">
   <URI><VALUE>http://publications.europa.eu/resource/cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1</VALUE><TYPE>cellar</TYPE><IDENTIFIER>9b84d482-85bd-11ed-9887-01aa75ed71a1</IDENTIFIER></URI>
   <SAMEAS><URI><VALUE>http://publications.europa.eu/resource/celex/32022L2555</VALUE><TYPE>celex</TYPE><IDENTIFIER>32022L2555</IDENTIFIER></URI></SAMEAS>
   <SAMEAS><URI><VALUE>http://publications.europa.eu/resource/eli/dir/2022/2555/oj</VALUE><TYPE>eli</TYPE><IDENTIFIER>dir:2022:2555:oj</IDENTIFIER></URI></SAMEAS>
</NOTICE>"""


def work_id(
    number: int
) -> str:
    return f"{number:08x}-0000-0000-0000-000000000000"


class FakeSparql(SparqlAPI):
    """SPARQL endpoint replaced by a function that answers the SELECT queries; records the queries it received."""

    def __init__(
        self,
        answer: Callable[[str], list[dict[str, str]]]
    ) -> None:
        super().__init__()
        self.answer = answer
        self.queries: list[str] = []

    def select(
        self,
        query: str
    ) -> list[dict[str, str]]:
        self.queries.append(query)
        return self.answer(query)


class TestConfiguration(unittest.TestCase):
    """Unit tests of the configuration (no network access)."""

    def test_seeds_are_main_acts(self):
        self.assertEqual(len(set(SEED_CELEX)), len(SEED_CELEX))
        for celex in SEED_CELEX:
            self.assertTrue(is_main_act(celex), celex)

    def test_act_pattern(self):
        self.assertTrue(is_main_act(NIS2_CELEX))
        self.assertFalse(is_main_act("32022L2555R(01)"))  # corrigendum
        self.assertFalse(is_main_act("02022L2555-20221227"))  # consolidated text
        self.assertFalse(is_main_act("62019CJ0311"))  # case law
        self.assertFalse(is_main_act("32009B0270"))  # budget

    def test_descriptors_are_disjoint(self):
        self.assertFalse(set(CORE_DESCRIPTORS) & set(ADJACENT_DESCRIPTORS))


class TestIdentifiers(unittest.TestCase):
    """Unit tests of the parsing of identifiers (no network access)."""

    def test_extract_identifiers(self):
        identifiers = CellarAPI.extract_identifiers(NOTICE)
        self.assertEqual(identifiers["cellar"], NIS2_WORK)
        self.assertEqual(identifiers["celex"], NIS2_CELEX)
        self.assertEqual(identifiers["eli"], "dir:2022:2555:oj")

    def test_celex_resource_id(self):
        request = CellarAPI.indentifiers_notice_request(CellarResourceId(CellarPS.CELEX, NIS2_CELEX))
        self.assertEqual(request.full_url, f"https://publications.europa.eu/resource/celex/{NIS2_CELEX}")
        self.assertEqual(request.get_header("Accept"), "application/xml;notice=identifiers")

    def test_webservice_references(self):
        references = [f"eng_cellar:{NIS2_WORK}_en", "eng_cellar:not-a-uuid_en", f"eng_cellar:{work_id(1)}_fr"]
        self.assertEqual(_work_ids_of(references), {NIS2_WORK, work_id(1)})

    def test_work_ids_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ids" / "work_ids.txt"
            write_work_ids(path, [(work_id(1), "32022L2555  seed"), (work_id(2), "")])
            self.assertEqual(read_work_ids(path), [work_id(1), work_id(2)])
            path.write_text(f"# comment\n\n{work_id(3)}\n{work_id(3)}  # again\n", encoding="utf-8")
            self.assertEqual(read_work_ids(path), [work_id(3)])
            path.write_text("not-a-uuid\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_work_ids(path)


class TestGatherer(unittest.TestCase):
    """Unit tests of the stages of the acquisition with a fake SPARQL endpoint (no network access)."""

    def test_queries_are_split_to_chunks(self):
        ids = [work_id(i) for i in range(_CHUNK_SIZE * 2 + 1)]
        sparql = FakeSparql(lambda query: [])
        WorkIdGatherer(sparql=sparql).celex_of(ids)
        self.assertEqual(len(sparql.queries), 3)
        for query in sparql.queries:
            self.assertLess(len(query), 4000)  # the endpoint rejects requests above about 6 KB

    def test_celex_of_keeps_only_main_acts(self):
        rows = [
            {"w": CELLAR + work_id(1), "celex": NIS2_CELEX},
            {"w": CELLAR + work_id(2), "celex": "32022L2555R(01)"},
            {"w": CELLAR + work_id(3), "celex": "62019CJ0311"},
        ]
        found = WorkIdGatherer(sparql=FakeSparql(lambda query: rows)).celex_of([work_id(1), work_id(2), work_id(3)])
        self.assertEqual(found, {work_id(1): NIS2_CELEX})

    def test_expansion_gate(self):
        members = [work_id(1), work_id(2), work_id(3)]
        # neighbour 10 is linked to all three members, 11 to two, 12 to one, 13 to one but tagged, 14 is linked to a member only as a corrigendum
        links = {10: members, 11: members[:2], 12: members[:1], 13: members[:1], 14: members[:1], 1: [work_id(2)]}

        def answer(query: str) -> list[dict[str, str]]:
            if "SELECT DISTINCT ?m ?n" in query:
                if "cdm:work_cites_work" not in query or "?m cdm:work_cites_work ?n" not in query:
                    return []
                return [{"m": CELLAR + m, "n": CELLAR + work_id(n)} for n, ms in links.items() for m in ms]
            return [
                {"w": CELLAR + work_id(10), "celex": "32020R0010", "tags": "0"},
                {"w": CELLAR + work_id(11), "celex": "32020R0011", "tags": "0"},
                {"w": CELLAR + work_id(12), "celex": "32020R0012", "tags": "0"},
                {"w": CELLAR + work_id(13), "celex": "32020R0013", "tags": "1"},
                {"w": CELLAR + work_id(14), "celex": "32020R0014R(01)", "tags": "1"},
            ]

        found = WorkIdGatherer(sparql=FakeSparql(answer)).expand(members, min_links=2, adjacent_descriptors=["5181"])
        self.assertEqual(found, {work_id(10): ("32020R0010", 3), work_id(11): ("32020R0011", 2), work_id(13): ("32020R0013", 1)})

    def test_coherence(self):
        ids = [work_id(1), work_id(2), work_id(3)]
        rows = [
            {"a": CELLAR + ids[0], "p": "http://publications.europa.eu/ontology/cdm#work_cites_work", "b": CELLAR + ids[1]},
            {"a": CELLAR + ids[0], "p": "http://publications.europa.eu/ontology/cdm#work_cites_work", "b": CELLAR + work_id(99)},
        ]
        coherence = WorkIdGatherer(sparql=FakeSparql(lambda query: rows)).coherence(ids)
        self.assertEqual(coherence["edges"], 1)
        self.assertEqual(coherence["edges_by_relation"], {"work_cites_work": 1})
        self.assertEqual(coherence["linked_works"], 2)
        self.assertEqual(coherence["isolated"], [ids[2]])

    def test_gather_records_provenance(self):
        gatherer = WorkIdGatherer(sparql=FakeSparql(lambda query: []), delay=0)
        gatherer.resolve_celex = lambda celex_numbers: {NIS2_CELEX: NIS2_WORK}
        gatherer.topic_sparql = lambda descriptors: {NIS2_WORK: NIS2_CELEX, work_id(1): CRA_CELEX}
        gatherer.expand = lambda collected, min_links, adjacent_descriptors: {work_id(2): ("32020R0002", 4)}
        result = gatherer.gather(seed_celex=[NIS2_CELEX], rounds=1)
        self.assertEqual(set(result.works), {NIS2_WORK, work_id(1), work_id(2)})
        self.assertEqual(result.works[NIS2_WORK].stages, {STAGE_SEED, STAGE_TOPIC})
        self.assertEqual(result.works[work_id(2)].stages, {STAGE_EXPANSION})
        self.assertEqual(result.works[work_id(2)].links, 4)
        self.assertEqual(result.stats["by_stage"], {STAGE_SEED: 1, STAGE_TOPIC: 2, STAGE_EXPANSION: 1})


class TestAcquisitionServices(unittest.TestCase):
    """Integration tests of the services used by the acquisition (require network access)."""

    _has_run_test = None

    def setUp(self):
        # Keep a delay between requests to avoid exceeding the service rate limit.
        if getattr(self.__class__, "_has_run_test", False):
            time.sleep(RATE_LIMIT_DELAY)
        self.__class__._has_run_test = True

    def test_resolve_celex_by_cellar_api(self):
        """Test that the Cellar API resolves a CELEX number to the work ID."""
        gatherer = WorkIdGatherer(delay=0)
        self.assertEqual(gatherer.resolve_celex([NIS2_CELEX]), {NIS2_CELEX: NIS2_WORK})

    def test_resolve_celex_by_sparql(self):
        """Test the SPARQL fallback of the CELEX resolution."""
        self.assertEqual(WorkIdGatherer().celex_lookup([NIS2_CELEX, CRA_CELEX]).get(NIS2_WORK), NIS2_CELEX)

    def test_topic_by_descriptor(self):
        """Test that the acts about information security (EuroVoc c_04ae3ba8) include NIS 2 and are main acts only."""
        found = WorkIdGatherer().topic_sparql(["c_04ae3ba8"])
        self.assertEqual(found.get(NIS2_WORK), NIS2_CELEX)
        self.assertTrue(all(is_main_act(celex) for celex in found.values()))

    def test_expansion_finds_linked_acts(self):
        """Test that the acts linked to NIS 2 and the Cyber Resilience Act are found and are not the collected ones."""
        gatherer = WorkIdGatherer()
        collected = gatherer.celex_lookup([NIS2_CELEX, CRA_CELEX, "32019R0881"])
        found = gatherer.expand(collected, min_links=2, adjacent_descriptors=[])
        self.assertTrue(found)
        self.assertFalse(set(found) & set(collected))
        self.assertTrue(all(links >= 2 for _, links in found.values()))

    def test_act_info(self):
        """Test the CELEX number and the descriptor check of a work (NIS 2 is tagged with 'information security')."""
        info = WorkIdGatherer().act_info([NIS2_WORK], ["c_04ae3ba8", "5181"])
        self.assertEqual(info, {NIS2_WORK: (NIS2_CELEX, True)})


if __name__ == "__main__":
    unittest.main()
