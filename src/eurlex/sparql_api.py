from __future__ import annotations

import json
from enum import Enum
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_SPARQL_ENDPOINT = "http://publications.europa.eu/webapi/rdf/sparql"

_DEFAULT_TIMEOUT = 60


class SparqlFormat(Enum):
    """Response formats supported by the SPARQL endpoint."""
    JSON = "application/sparql-results+json"
    XML = "application/sparql-results+xml"
    CSV = "text/csv"
    TSV = "text/tab-separated-values"
    RDF_XML = "application/rdf+xml"
    TURTLE = "text/turtle"


class SparqlAPI:
    """
    Wrapper class for the Publications Office SPARQL endpoint.

    The queries are passed as plain strings, the wrapper only sends them and parses the response.

    Args:
        endpoint (str): The URL of the SPARQL endpoint. Default "http://publications.europa.eu/webapi/rdf/sparql".
        timeout (int): The request timeout in seconds. Default 60.
    """

    def __init__(
        self,
        endpoint: str = _SPARQL_ENDPOINT,
        timeout: int = _DEFAULT_TIMEOUT
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def build_request(
        self,
        query: str,
        response_format: SparqlFormat = SparqlFormat.JSON
    ) -> Request:
        """
        Build the HTTP request that sends the SPARQL query to the endpoint.

        The query is sent in the body of a POST request, so long queries are not limited by the URL length.

        Args:
            query (str): The SPARQL query string.
            response_format (SparqlFormat): The requested format of the response. Default ``SparqlFormat.JSON``.

        Returns:
            Request: The prepared HTTP request.
        """
        return Request(
            url=self.endpoint,
            data=urlencode({"query": query}).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": response_format.value,
            },
        )

    def execute(
        self,
        query: str,
        response_format: SparqlFormat = SparqlFormat.JSON
    ) -> str:
        """
        Send the SPARQL query to the endpoint and return the raw response body.

        Use the RDF formats (``RDF_XML``, ``TURTLE``) for CONSTRUCT and DESCRIBE queries and the result formats
        (``JSON``, ``XML``, ``CSV``, ``TSV``) for SELECT and ASK queries.

        The public endpoint rejects large requests with HTTP 403 (the limit is somewhere above 6 KB), so a long list of
        URIs in a query has to be split into several queries.

        Args:
            query (str): The SPARQL query string.
            response_format (SparqlFormat): The requested format of the response. Default ``SparqlFormat.JSON``.

        Returns:
            str: The response body as a string.

        Raises:
            HTTPError: If the endpoint returns an HTTP error (e.g. 400 for a malformed query).
            URLError: If there's a connection error.
        """
        request = self.build_request(query, response_format)

        with urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    @staticmethod
    def parse_bindings(
        response_json: str
    ) -> list[dict[str, str]]:
        """
        Extract the result rows from a SPARQL JSON response of a SELECT query.

        Args:
            response_json (str): The response body in ``SparqlFormat.JSON`` format.

        Returns:
            list[dict[str, str]]: One dictionary per result row, mapping the variable name to its value. Unbound
                variables are not present in the row.
        """
        data = json.loads(response_json)
        return [
            {variable: term["value"] for variable, term in binding.items()}
            for binding in data.get("results", {}).get("bindings", [])
        ]

    @staticmethod
    def parse_boolean(
        response_json: str
    ) -> bool:
        """
        Extract the result of a SPARQL JSON response of an ASK query.

        Args:
            response_json (str): The response body in ``SparqlFormat.JSON`` format.

        Returns:
            bool: The result of the ASK query.

        Raises:
            ValueError: If the response is not a result of an ASK query.
        """
        data = json.loads(response_json)
        if "boolean" not in data:
            raise ValueError("The response does not contain a boolean result")
        return bool(data["boolean"])

    def select(
        self,
        query: str
    ) -> list[dict[str, str]]:
        """
        Run a SELECT query and return its result rows.

        Args:
            query (str): The SPARQL SELECT query string.

        Returns:
            list[dict[str, str]]: One dictionary per result row, mapping the variable name to its value.

        Raises:
            HTTPError: If the endpoint returns an HTTP error.
            URLError: If there's a connection error.
        """
        return self.parse_bindings(self.execute(query, SparqlFormat.JSON))

    def ask(
        self,
        query: str
    ) -> bool:
        """
        Run an ASK query and return its result.

        Args:
            query (str): The SPARQL ASK query string.

        Returns:
            bool: The result of the ASK query.

        Raises:
            HTTPError: If the endpoint returns an HTTP error.
            URLError: If there's a connection error.
            ValueError: If the response is not a result of an ASK query.
        """
        return self.parse_boolean(self.execute(query, SparqlFormat.JSON))
