from __future__ import annotations

from types import TracebackType
from typing import LiteralString, Optional, cast

from neo4j import GraphDatabase, ManagedTransaction, Query, ResultSummary


NEO4J_DEFAULT_HOST = "localhost"
NEO4J_DEFAULT_PORT = 7687
NEO4J_DEFAULT_USER = "neo4j"
NEO4J_DEFAULT_PASSWORD = "password"


class Neo4jDatabase:
    """
    Wrapper class for interacting with a Neo4j database.

    Args:
        host (str): The Neo4j host (default: "localhost").
        port (int): The Neo4j port (default: 7687).
        user (str): The Neo4j username (default: "neo4j").
        password (str): The Neo4j password (default: "password").
    """
    def __init__(
        self,
        host: str = NEO4J_DEFAULT_HOST,
        port: int = NEO4J_DEFAULT_PORT,
        user: str = NEO4J_DEFAULT_USER,
        password: str = NEO4J_DEFAULT_PASSWORD
    ) -> None:
        self._uri = f"bolt://{host}:{port}"
        self._driver = GraphDatabase.driver(self._uri, auth=(user, password))

    def __enter__(self) -> Neo4jDatabase:
        """
        Enter the context manager and return the database wrapper.
        """
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType]
    ) -> None:
        """
        Exit the context manager and close the connection to the Neo4j database.

        Args:
            exc_type (Optional[type[BaseException]]): The type of the exception raised in the ``with`` block, if any.
            exc_value (Optional[BaseException]): The exception raised in the ``with`` block, if any.
            traceback (Optional[TracebackType]): The traceback of the exception raised in the ``with`` block, if any.
        """
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
            query (LiteralString | Query): The Cypher query string.
            parameters (Optional[dict]): Optional dictionary of query parameters.

        Returns:
            list[dict]: A list of dictionaries representing the query results.
        """
        with self._driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def run_write(
        self,
        query: str,
        parameters: Optional[dict] = None
    ) -> dict[str, int]:
        """
        Run a write query in a managed transaction and return what it changed.

        The driver only accepts literal strings inside transaction functions, but the loader composes statements from
        validated labels and relationship types; every value is passed as a parameter, never interpolated.

        Args:
            query (str): The Cypher query string.
            parameters (Optional[dict]): Optional dictionary of query parameters.

        Returns:
            dict[str, int]: Counters of the query summary: nodes_created, relationships_created, properties_set,
                labels_added, ...
        """
        def work(
            tx: ManagedTransaction
        ) -> ResultSummary:
            """
            Run the query in the managed transaction.

            Args:
                tx (ManagedTransaction): The managed transaction.

            Returns:
                ResultSummary: The summary of the consumed result.
            """
            return tx.run(cast(LiteralString, query), parameters or {}).consume()

        with self._driver.session() as session:
            summary = session.execute_write(work)
        c = summary.counters
    
        return {
            "nodes_created": c.nodes_created,
            "nodes_deleted": c.nodes_deleted,
            "relationships_created": c.relationships_created,
            "relationships_deleted": c.relationships_deleted,
            "properties_set": c.properties_set,
            "labels_added": c.labels_added,
            "constraints_added": c.constraints_added,
            "indexes_added": c.indexes_added,
        }

    def import_RDF_data(
        self,
        rdf_data: str
    ) -> None:
        """
        Import RDF data into the Neo4j database using the n10s plugin.

        Args:
            rdf_data (str): The RDF data in string format.
        """
        query = """CALL n10s.rdf.import.inline($rdf_data, "RDF/XML")"""
        self.run_query(query, {"rdf_data": rdf_data})