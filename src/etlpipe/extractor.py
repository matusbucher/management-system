from urllib.request import urlopen
from rdflib import Graph

from src.eurlex.cellar_api import CellarResourceId, CellarAPI

from .interfaces import ExtractorInterface


class CellarExtractor(ExtractorInterface):
    """
    Extractor for retrieving RDF data from the Cellar API.
    """

    def extract(
        self,
        resource_id: CellarResourceId
    ) -> Graph:
        """
        Extract RDF data from the Cellar API for the given resource ID.

        Args:
            resource_id (CellarResourceId): The ID of the resource to extract.

        Returns:
            Graph: An RDF graph containing the extracted data.
        """
        req = CellarAPI.metadata_request(resource_id)
        with urlopen(req) as response:
            data = response.read()
        graph = Graph()
        graph.parse(data=data, format="xml")
        return graph