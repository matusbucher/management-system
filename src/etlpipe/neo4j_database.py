from neo4j import GraphDatabase, Query

from typing import LiteralString, Optional

from .constants import *


class Neo4jDatabase:
    """
    Wrapper class for interacting with a Neo4j database.

    Args:
        host: The Neo4j host (default: "localhost").
        port: The Neo4j port (default: 7687).
        user: The Neo4j username (default: "neo4j").
        password: The Neo4j password (default: "password").
    """
    def __init__(
        self,
        host: str = NEO4J_DEFAULT_HOST,
        port: int = NEO4J_DEFAULT_PORT,
        user: str = NEO4J_DEFAULT_USER,
        password: str = NEO4J_DEFAULT_PASSWORD
    ):
        self._uri = f"bolt://{host}:{port}"
        self._driver = GraphDatabase.driver(self._uri, auth=(user, password))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self) -> None:
        """
        Close the connection to the Neo4j database.
        """
        self._driver.close()
    
    def verify_connection(self) -> None:
        """
        Verify the connectivity to the Neo4j database.

        Raises:
            neo4j.exceptions.ServiceUnavailable: If the database is not reachable.
        """
        self._driver.verify_connectivity()

    def run_query(
        self,
        query: LiteralString | Query,
        parameters: Optional[dict] = None
    ) -> list[dict]:
        """
        Run a Cypher query against the Neo4j database.

        Args:
            query: The Cypher query string.
            parameters: Optional dictionary of query parameters.

        Returns:
            A list of dictionaries representing the query results.
        """
        with self._driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def import_RDF_data(
        self,
        rdf_data: str
    ) -> None:
        query = """
        CALL n10s.rdf.import.inline($rdf_data, "RDF/XML")
        """
        self.run_query(query, {"rdf_data": rdf_data})
