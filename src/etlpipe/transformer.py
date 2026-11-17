from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional, Sequence

from rdflib import Graph

from .context import TransformContext
from .interfaces import Transformer
from .report import StepReport
from .steps import AliasResolver, AnnotationCleaner, AttributeMapper, LifecycleEnricher, PredicateFilter, RelationCanonicalizer, ScopeFilter, TypeReducer, WemiLevelFilter


_HEADLINE_COUNTERS = (
    "alias_groups",
    "uris_merged",
    "nodes_removed",
    "dropped",
    "relation_triples_in",
    "duplicates_folded",
    "edges_out",
    "triples_inverted",
    "axioms_out",
    "axioms_headless_removed",
    "attribute_triples_out",
    "citations_dropped"
)

_TRANSFORM_LOGGER_NAME = "etlpipe.transform"

logger = logging.getLogger(_TRANSFORM_LOGGER_NAME)


class TransformerChain(Transformer):
    """
    Wrapper for a sequence of transformer steps. Runs transformer steps one after another and
    records statistics for each.

    The chain is itself a :class:`Transformer`, so chains can be nested. With
    ``snapshot_dir`` the graph after every step is serialised to Turtle for inspection.

    Args:
        steps (Sequence[Transformer]): The sequence of transformer steps to run.
        snapshot_dir (Optional[Path]): The directory to save snapshots of the graph after each step. If None, no
            snapshots are saved. Default None.
    """

    name = "chain"

    def __init__(
        self,
        steps: Sequence[Transformer],
        snapshot_dir: Optional[Path] = None
    ) -> None:
        self.steps = list(steps)
        self.snapshot_dir = snapshot_dir

    def transform(
        self,
        graph: Graph,
        ctx: TransformContext
    ) -> Graph:
        """
        Transform the given RDF graph using the sequence of transformer steps.

        Args:
            graph (Graph): The RDF graph to transform.
            ctx (TransformContext): The transformation context containing metadata and statistics.

        Returns:
            Graph: The transformed RDF graph.
        """
        for index, step in enumerate(self.steps, start=1):
            stats = ctx.begin_step(step.name, len(graph))
            started = time.perf_counter()
            graph = step.transform(graph, ctx)
            stats.duration_s = time.perf_counter() - started
            stats.triples_out = len(graph)
            self._log(ctx, stats)
            if self.snapshot_dir is not None:
                self._snapshot(graph, ctx, index, step.name)
        return graph

    @staticmethod
    def _log(
        ctx: TransformContext,
        stats: StepReport
    ) -> None:
        """
        Log the transformation step statistics.

        Args:
            ctx (TransformContext): The transformation context.
            stats (StepReport): The statistics of the transformation step.
        """
        headline = ", ".join(f"{counter}={stats.counters[counter]:,}" for counter in _HEADLINE_COUNTERS if stats.counters.get(counter))
        logger.info(
            "[%s] %s: %s -> %s triples (%+d) in %.2fs%s",
            ctx.source or "-",
            stats.name,
            f"{stats.triples_in:,}",
            f"{stats.triples_out:,}",
            stats.triples_delta,
            stats.duration_s,
            f" | {headline}" if headline else ""
        )
        
        for message in stats.warnings:
            logger.warning("[%s] %s: %s", ctx.source or "-", stats.name, message)
        
        if logger.isEnabledFor(logging.DEBUG):
            for key, value in sorted(stats.counters.items()):
                logger.debug("[%s] %s counter %s=%s", ctx.source or "-", stats.name, key, f"{value:,}")
            for group, counter in stats.breakdowns.items():
                top = ", ".join(f"{k}={v:,}" for k, v in counter.most_common(15))
                logger.debug("[%s] %s breakdown %s: %s", ctx.source or "-", stats.name, group, top)

    def _snapshot(
        self,
        graph: Graph,
        ctx: TransformContext,
        index: int,
        name: str
    ) -> None:
        """
        Take a snapshot of the current RDF graph by serializing it to a Turtle file.

        Args:
            graph (Graph): The RDF graph to snapshot.
            ctx (TransformContext): The transformation context.
            index (int): The index of the current transformation step.
            name (str): The name of the current transformation step.
        """
        if self.snapshot_dir is None:
            return
        folder = self.snapshot_dir / (ctx.source or "document")
        folder.mkdir(parents=True, exist_ok=True)
        graph.serialize(destination=folder / f"{index:02d}_{name}.ttl", format="turtle")

    @staticmethod
    def default_chain(
        snapshot_dir: Optional[Path] = None
    ) -> TransformerChain:
        """
        Return a default transformer chain with the standard sequence of transformation steps.

        AliasResolver -> WemiLevelFilter -> PredicateFilter -> RelationCanonicalizer ->
        AttributeMapper -> AnnotationCleaner -> TypeReducer -> LifecycleEnricher -> ScopeFilter

        Args:
            snapshot_dir (Optional[Path]): The directory to save snapshots of the graph after each step. If None, no
                snapshots are saved.

        Returns:
            TransformerChain: The chain with the standard transformer steps.
        """
        default_steps = [
            AliasResolver(),
            WemiLevelFilter(),
            PredicateFilter(),
            RelationCanonicalizer(),
            AttributeMapper(),
            AnnotationCleaner(),
            TypeReducer(),
            LifecycleEnricher(),
            ScopeFilter(),
        ]
        return TransformerChain(default_steps, snapshot_dir=snapshot_dir)