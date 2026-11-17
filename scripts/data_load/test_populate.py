import json
import sys
import tempfile
import unittest
from pathlib import Path

workspace_root = Path(__file__).resolve().parents[2]
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from scripts.data_load.database_setup import DatabaseSetup, _chunks
from scripts.data_load.populate_database import document_statistics, phase, populate_parse_args, previous_successes
from scripts.data_load.summary import render_summary
from src.etlpipe.report import ExtractReport, LoadReport, PipelineReport, TransformReport
from src.eurlex.sparql_api import SparqlAPI


def report(
    source: str,
    triples: int = 100,
    nodes: int = 10,
    relationships: int = 20,
    error: str = ""
) -> PipelineReport:
    result = PipelineReport(source=source)
    result.extract = ExtractReport(triples=triples, duration_s=1.0)
    result.duration_s = 3.0
    if error:
        result.error = error
    else:
        result.load = LoadReport(nodes_projected=nodes, relationships_projected=relationships, duration_s=0.5)
        result.load.db_counters.update({"nodes_created": nodes, "relationships_created": relationships})
    return result


class FakeDb:
    """Neo4j wrapper that records the queries and answers them with canned rows chosen by a substring of the query."""

    def __init__(
        self,
        answers: dict[str, list[dict]]
    ) -> None:
        self.answers = answers
        self.queries: list[str] = []
        self.writes: list[tuple[str, dict]] = []

    def run_query(
        self,
        query: str,
        parameters: dict | None = None
    ) -> list[dict]:
        self.queries.append(query)
        return next((rows for key, rows in self.answers.items() if key in query), [])

    def run_write(
        self,
        query: str,
        parameters: dict | None = None
    ) -> dict[str, int]:
        self.writes.append((query, parameters or {}))
        return {}


class FakeSparql(SparqlAPI):
    def __init__(
        self,
        labels: dict[str, str]
    ) -> None:
        super().__init__()
        self.labels = labels

    def select(
        self,
        query: str
    ) -> list[dict[str, str]]:
        return [{"c": uri, "label": label} for uri, label in self.labels.items() if f"<{uri}>" in query]


class TestPopulationLogic(unittest.TestCase):
    """Unit tests of the population scripts (no database and no network access)."""

    def test_arguments(self):
        args = populate_parse_args([])
        self.assertEqual(args.work_ids_file.name, "work_ids.txt")
        self.assertFalse(args.reset)
        self.assertIsNone(args.limit)
        args = populate_parse_args(["--limit", "3", "--resume", "some/dir", "--no-lifecycle"])
        self.assertEqual((args.limit, str(args.resume).replace("\\", "/"), args.no_lifecycle), (3, "some/dir", True))

    def test_phase_records_success_and_failure(self):
        summary = {"phases": {}}
        with phase(summary, "first", 1, 2) as record:
            record["answer"] = 42
        self.assertEqual(summary["phases"]["first"]["status"], "ok")
        self.assertEqual(summary["phases"]["first"]["answer"], 42)
        with self.assertRaises(ValueError):
            with phase(summary, "second", 2, 2):
                raise ValueError("boom")
        self.assertEqual(summary["phases"]["second"]["status"], "failed")
        self.assertIn("boom", summary["phases"]["second"]["error"])
        self.assertIn("duration_s", summary["phases"]["second"])

    def test_phase_can_be_marked_skipped(self):
        summary = {"phases": {}}
        with phase(summary, "optional", 1, 1) as record:
            record["status"] = "skipped"
        self.assertEqual(summary["phases"]["optional"]["status"], "skipped")

    def test_previous_successes(self):
        with tempfile.TemporaryDirectory() as directory:
            documents = Path(directory)
            (documents / "good.json").write_text(json.dumps({"error": None}), encoding="utf-8")
            (documents / "bad.json").write_text(json.dumps({"error": "RuntimeError: boom"}), encoding="utf-8")
            (documents / "broken.json").write_text("{not json", encoding="utf-8")
            (documents / "aggregate.json").write_text("{}", encoding="utf-8")
            self.assertEqual(previous_successes(documents), {"good"})
            self.assertEqual(previous_successes(documents / "missing"), set())

    def test_document_statistics(self):
        stats = document_statistics([report("a", 100, 10, 20), report("b", 50, 5, 5), report("c", error="RuntimeError: x")], ["skipped"])
        self.assertEqual((stats["processed"], stats["ok"], stats["failed"], stats["skipped_already_loaded"]), (3, 2, 1, 1))
        self.assertEqual(stats["extracted_triples"], 250)
        self.assertEqual((stats["nodes_projected"], stats["relationships_projected"]), (15, 25))
        self.assertEqual(stats["database_counters"], {"nodes_created": 15, "relationships_created": 25})
        self.assertEqual(stats["failures"], [{"work_id": "c", "error": "RuntimeError: x"}])

    def test_summary_renders_without_data_of_later_phases(self):
        text = render_summary({"started_at": "t", "run_dir": "d", "phases": {"environment": {"status": "failed", "duration_s": 1.0}}, "exit_code": 2, "error": "boom"})
        self.assertIn("**failed**", text)
        self.assertIn("| documents | not run | - |", text)

    def test_summary_renders_statistics(self):
        statistics = {
            "status": "ok", "duration_s": 1.0, "nodes": 10, "relationships": 5,
            "nodes_by_label": {f"L{i}": 100 - i for i in range(30)},
            "relationships_by_type": {"CITES": 5},
            "works": {"loaded": 4, "stub": 3}, "works_duplicated_by_celex": 0, "requested_works": {"listed": 2, "present": 2},
            "most_connected_works": [{"celex": "32022L2555", "uri": "u", "degree": 7}],
        }
        text = render_summary({"started_at": "t", "run_dir": "d", "phases": {"statistics": statistics}, "exit_code": 0})
        self.assertIn("the 20 largest of 30", text)
        self.assertIn("* L19: 81", text)
        self.assertNotIn("* L20:", text)
        self.assertIn("Requested works present in the database: 2 of 2.", text)
        self.assertIn("* CITES: 5", text)
        self.assertIn("32022L2555: 7 relationships", text)

    def test_chunks(self):
        self.assertEqual(list(_chunks(["a", "b", "c"], 2)), [["a", "b"], ["c"]])


class TestDatabaseSetup(unittest.TestCase):
    """Unit tests of the database setup with a fake database (no database and no network access)."""

    def test_n10s_is_configured_once(self):
        db = FakeDb({"graphconfig.show": [{"param": "x"}]})
        self.assertFalse(DatabaseSetup(db).configure_n10s())
        self.assertFalse(any("graphconfig.init" in query for query in db.queries))
        db = FakeDb({"graphconfig.show": []})
        self.assertTrue(DatabaseSetup(db).configure_n10s())
        self.assertTrue(any("graphconfig.init" in query for query in db.queries))

    def test_ontology_is_not_imported_twice(self):
        db = FakeDb({"n4sch__Class": [{"n": 576}], "n4sch__Relationship": [{"n": 1}], "n4sch__Property": [{"n": 2}]})
        result = DatabaseSetup(db).import_ontology()
        self.assertFalse(result["imported"])
        self.assertEqual(result["counts"], {"classes": 576, "relationships": 1, "properties": 2})
        self.assertFalse(any("onto.import" in query for query in db.queries))

    def test_labels_are_set_for_resolved_concepts_only(self):
        uris = ["http://eurovoc.europa.eu/1", "http://eurovoc.europa.eu/2"]
        db = FakeDb({"RETURN n.uri AS uri": [{"uri": uri} for uri in uris]})
        result = DatabaseSetup(db).enrich_labels(FakeSparql({uris[0]: "first"}))
        self.assertEqual(result, {"missing": 2, "labelled": 1, "unresolved": 1})
        self.assertEqual(db.writes[0][1], {"rows": [{"uri": uris[0], "label": "first"}]})


if __name__ == "__main__":
    unittest.main()
