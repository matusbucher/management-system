import sys
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError

workspace_root = Path(__file__).parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from src.eurlex.sparql_api import SparqlAPI, SparqlFormat

RATE_LIMIT_DELAY = 1

NIS2_CELEX = "32022L2555"
NIS2_WORK = "http://publications.europa.eu/resource/cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1"

CELEX_QUERY = f"""
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?work WHERE {{ ?work cdm:resource_legal_id_celex "{NIS2_CELEX}"^^xsd:string }}
"""


class TestSparqlRequest(unittest.TestCase):
    """Unit tests of the request building and response parsing (no network access)."""

    def test_build_request(self):
        request = SparqlAPI().build_request("SELECT * WHERE { ?s ?p ?o } LIMIT 1", SparqlFormat.CSV)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "http://publications.europa.eu/webapi/rdf/sparql")
        self.assertEqual(request.get_header("Accept"), "text/csv")
        self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")
        self.assertEqual(request.data, b"query=SELECT+%2A+WHERE+%7B+%3Fs+%3Fp+%3Fo+%7D+LIMIT+1")

    def test_custom_endpoint(self):
        request = SparqlAPI("http://localhost:3030/sparql").build_request("ASK {}")
        self.assertEqual(request.full_url, "http://localhost:3030/sparql")
        self.assertEqual(request.get_header("Accept"), SparqlFormat.JSON.value)

    def test_parse_bindings(self):
        response = '{"head": {"vars": ["a", "b"]}, "results": {"bindings": [' \
                   '{"a": {"type": "uri", "value": "http://x/1"}, "b": {"type": "literal", "value": "one"}},' \
                   '{"a": {"type": "uri", "value": "http://x/2"}}]}}'
        self.assertEqual(
            SparqlAPI.parse_bindings(response),
            [{"a": "http://x/1", "b": "one"}, {"a": "http://x/2"}]
        )

    def test_parse_bindings_empty(self):
        self.assertEqual(SparqlAPI.parse_bindings('{"head": {"vars": []}, "results": {"bindings": []}}'), [])

    def test_parse_boolean(self):
        self.assertTrue(SparqlAPI.parse_boolean('{"head": {}, "boolean": true}'))
        self.assertFalse(SparqlAPI.parse_boolean('{"head": {}, "boolean": false}'))
        with self.assertRaises(ValueError):
            SparqlAPI.parse_boolean('{"head": {"vars": []}, "results": {"bindings": []}}')


class TestSparqlAPI(unittest.TestCase):
    """Integration tests for the SparqlAPI (require network access)."""

    _has_run_test = None

    def setUp(self):
        # Keep a delay between requests to avoid exceeding the service rate limit.
        if getattr(self.__class__, "_has_run_test", False):
            time.sleep(RATE_LIMIT_DELAY)
        self.__class__._has_run_test = True

    def test_select(self):
        """Test a SELECT query that finds a work by its CELEX number."""
        rows = SparqlAPI().select(CELEX_QUERY)
        self.assertEqual(rows, [{"work": NIS2_WORK}])

    def test_ask(self):
        """Test ASK queries for an existing and a non-existing work."""
        sparql = SparqlAPI()
        self.assertTrue(sparql.ask(f"ASK {{ <{NIS2_WORK}> ?p ?o }}"))
        self.assertFalse(sparql.ask("ASK { <http://publications.europa.eu/resource/cellar/00000000-0000-0000-0000-000000000000> ?p ?o }"))

    def test_construct(self):
        """Test a CONSTRUCT query returning RDF in Turtle."""
        turtle = SparqlAPI().execute(
            f"CONSTRUCT {{ <{NIS2_WORK}> ?p ?o }} WHERE {{ <{NIS2_WORK}> ?p ?o }} LIMIT 5",
            SparqlFormat.TURTLE
        )
        self.assertIn(NIS2_WORK, turtle)

    def test_csv_format(self):
        """Test that the response format follows the Accept header."""
        csv = SparqlAPI().execute(CELEX_QUERY, SparqlFormat.CSV)
        self.assertTrue(csv.startswith('"work"'))
        self.assertIn(NIS2_WORK, csv)

    def test_malformed_query(self):
        """Test that a malformed query is reported as an HTTP error."""
        with self.assertRaises(HTTPError) as context:
            SparqlAPI().select("SELECT WHERE {")
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
