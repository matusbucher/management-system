from rdflib import Graph

from .interfaces import LoaderInterface


class Loader(LoaderInterface):
    def load(self, rdf_graph: Graph) -> None:
        # Implement the loading logic here
        pass