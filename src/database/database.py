from neo4j import GraphDatabase

NEO4J_HOST = "localhost"
NEO4J_PORT = 7687
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

class Neo4jDatabase:
    def __init__(self, host=NEO4J_HOST, port=NEO4J_PORT, user=NEO4J_USER, password=NEO4J_PASSWORD):
        self._uri = f"bolt://{host}:{port}"
        self._driver = GraphDatabase.driver(self._uri, auth=(user, password))

    def verify_connection(self):
        self._driver.verify_connectivity()

    def close(self):
        self._driver.close()

    def run_query(self, query, parameters=None):
        with self._driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def import_RDF_data(self, rdf_data):
        query = """
        CALL n10s.rdf.import.inline($rdf_data, "RDF/XML")
        """
        self.run_query(query, {"rdf_data": rdf_data})
