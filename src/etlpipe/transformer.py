from rdflib import Graph

from .interfaces import TransformerInterface


class Transformer(TransformerInterface):
    def transform(self, rdf_graph: Graph) -> Graph:
        # Implement the transformation logic here
        return rdf_graph