from typing import Protocol
from rdflib import Graph

from src.eurlex.cellar_api import CellarResourceId


class ExtractorInterface(Protocol):
    def extract(self, resource_id: CellarResourceId) -> Graph: ...


class TransformerInterface(Protocol):
    def transform(self, rdf_graph: Graph) -> Graph: ...


class LoaderInterface(Protocol):
    def load(self, rdf_graph: Graph) -> None: ...