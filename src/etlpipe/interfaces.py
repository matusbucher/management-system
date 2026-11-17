from abc import ABC, abstractmethod
from typing import Any, Optional

from rdflib import Graph

from .context import LoadContext, TransformContext
from .report import LoadReport


class Extractor(ABC):
    """
    Extractor interface for producing raw RDF graphs from various sources.
    """
    @abstractmethod
    def extract(
        self,
        source: Any
    ) -> Graph:
        """
        Extracts the raw RDF graph from the given ``source`` (e.g. a ``CellarResourceId`` or a file path).

        Args:
            source (Any): The input source from which to extract the RDF graph.

        Returns:
            Graph: The extracted RDF graph.
        """
        pass


class Transformer(ABC):
    """
    Transformer interface for modifying RDF graphs.

    Attributes:
        name (str): The name of the transformer step.
    """
    name: str

    @abstractmethod
    def transform(
        self,
        graph: Graph,
        ctx: TransformContext
    ) -> Graph:
        """
        Transforms the given RDF graph using options from the provided context and updates
        the context with transformation statistics.

        Args:
            graph (Graph): The input RDF graph to transform.
            ctx (TransformContext): The context containing transformation options and statistics.

        Returns:
            Graph: The transformed RDF graph.
        """
        pass


class Loader(ABC):
    """
    Loader interface for writing RDF graphs to a target store.
    """
    @abstractmethod
    def load(
        self,
        graph: Graph,
        ctx: Optional[LoadContext] = None
    ) -> LoadReport:
        """
        Loads the given RDF graph into the target store.

        Optional context can be provided to influence the loading process.

        Args:
            graph (Graph): The RDF graph to load.
            ctx (Optional[LoadContext]): The context containing loading options and statistics.

        Returns:
            LoadReport: The report summarizing the loading process.
        """
        pass