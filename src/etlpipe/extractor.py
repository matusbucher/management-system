from pathlib import Path

from rdflib import Graph
from urllib.request import urlopen

from src.eurlex.cellar_api import CellarResourceId, CellarAPI

from .interfaces import Extractor


class CellarExtractor(Extractor):
    """
    Extractor for retrieving RDF data from the Cellar API.
    """

    def extract(
        self,
        source: CellarResourceId
    ) -> Graph:
        """
        Extract RDF data from the Cellar API for the given resource ID.

        Args:
            source (CellarResourceId): The ID of the resource to extract.

        Returns:
            Graph: An RDF graph containing the extracted data.
        """
        req = CellarAPI.metadata_request(source)
        with urlopen(req) as response:
            data = response.read()
        graph = Graph()
        graph.parse(data=data, format="xml")
        return graph


class FileExtractor(Extractor):
    """
    Reads RDF data from a local file.
    """

    def extract(
        self,
        source: str | Path
    ) -> Graph:
        """
        Extract RDF data from a local file.

        Args:
            source (str | Path): The path to the RDF file.

        Returns:
            Graph: An RDF graph containing the extracted data.
        """
        graph = Graph()
        graph.parse(source, format="xml")
        return graph