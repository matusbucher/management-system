from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

import json
import logging
import time

from .context import LoadContext, TransformContext, TransformOptions
from .interfaces import Extractor, Loader, Transformer
from .report import PipelineReport, aggregate_reports
from .summary import summarize_graph
from .transformer import TransformerChain


_PIPELINE_LOGGER_NAME = "etlpipe.pipeline"

logger = logging.getLogger(_PIPELINE_LOGGER_NAME)


class EtlPipeline:
    """
    Runs the ETL stages for one or many documents and returns a :class:`PipelineReport` per document.

    Args:
        extractor (Extractor): Produces the raw RDF graph of a document.
        transformer (Optional[Transformer]): The transformer (chain); defaults to :func:`default_chain`.
        loader (Optional[Loader]): Optional - without it the pipeline only transforms (useful for analysis and reports).
        options (Optional[TransformOptions]): Switches of the transformer chain.
        report_dir (Optional[Path]): If set, every run writes ``<name>.json`` and appends a line to ``runs.jsonl``
            there.
        top (Optional[int]): Keep only the ``top`` largest entries of each breakdown in the written reports
            (``None`` = all).
    """

    def __init__(
        self,
        extractor: Extractor,
        transformer: Optional[Transformer] = None,
        loader: Optional[Loader] = None,
        options: Optional[TransformOptions] = None,
        report_dir: Optional[Path] = None,
        top: Optional[int] = None
    ) -> None:
        self.extractor = extractor
        self.transformer = transformer or TransformerChain.default_chain()
        self.loader = loader
        self.options = options or TransformOptions()
        self.report_dir = report_dir
        self.top = top

    def run(
        self,
        source: Any,
        name: Optional[str] = None,
        dry_run: bool = False
    ) -> PipelineReport:
        """
        Run the extract, transform and (optionally) load stages for one document.

        A failing stage does not raise; the error is stored in the returned report.

        Args:
            source (Any): The input of the extractor (e.g. a ``CellarResourceId`` or a file path).
            name (Optional[str]): The name of the document in logs and reports. Defaults to the file stem or
                ``str(source)``.
            dry_run (bool): If True, the loader only projects the graph and writes nothing. Default False.

        Returns:
            PipelineReport: The report of the run.
        """
        name = name or (Path(source).stem if isinstance(source, (str, Path)) and Path(source).suffix else str(source))
        report = PipelineReport(source=name)
        started = time.perf_counter()
        try:
            t0 = time.perf_counter()
            graph = self.extractor.extract(source)
            report.extract.source = str(source)
            report.extract.triples = len(graph)
            report.extract.duration_s = time.perf_counter() - t0
            logger.info("[%s] extract: %s triples in %.2fs", name, f"{len(graph):,}", report.extract.duration_s)

            ctx = TransformContext(options=self.options, source=name, report=report.transform)
            graph = self.transformer.transform(graph, ctx)
            report.graph = summarize_graph(graph)
            logger.info("[%s] canonical graph: %s nodes, %s edges (%s annotated)", name, f"{report.graph['nodes']:,}",
                        f"{report.graph['edges']:,}", f"{report.graph['annotated_edges']:,}")

            if self.loader is not None:
                report.load = self.loader.load(graph, LoadContext(source=name, dry_run=dry_run))
        except Exception as exc:  # one failing document must not stop a batch; the error is part of the report
            logger.exception("[%s] pipeline failed", name)
            report.error = f"{type(exc).__name__}: {exc}"
        report.duration_s = time.perf_counter() - started
        self._write(report)
        return report

    def run_many(
        self,
        sources: Iterable[Any],
        dry_run: bool = False,
        stop_on_error: bool = False
    ) -> list[PipelineReport]:
        """
        Run the pipeline for every source.

        Args:
            sources (Iterable[Any]): The inputs of the extractor.
            dry_run (bool): If True, the loader only projects the graph and writes nothing. Default False.
            stop_on_error (bool): If True, stop after the first failed document. Default False.

        Returns:
            list[PipelineReport]: The reports of the processed documents.
        """
        reports: list[PipelineReport] = []
        for source in sources:
            report = self.run(source, dry_run=dry_run)
            reports.append(report)
            if report.error and stop_on_error:
                break
        return reports

    def write_aggregate(
        self,
        reports: list[PipelineReport],
        filename: str = "aggregate.json"
    ) -> Optional[Path]:
        """
        Write the per-step statistics summed over ``reports`` (needs ``report_dir``).

        Args:
            reports (list[PipelineReport]): The reports to aggregate.
            filename (str): The name of the written file inside ``report_dir``. Default "aggregate.json".

        Returns:
            Optional[Path]: The path of the written file, or None if there is no ``report_dir`` or no reports.
        """
        if self.report_dir is None or not reports:
            return None
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / filename
        path.write_text(json.dumps(aggregate_reports(reports), ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("aggregate report written to %s", path)
        return path

    def _write(
        self,
        report: PipelineReport
    ) -> None:
        """
        Write the report of a run to ``report_dir`` (if set).

        Args:
            report (PipelineReport): The report to write.
        """
        if self.report_dir is None:
            return
        report.write_json(self.report_dir / f"{report.source}.json", self.top)
        report.append_jsonl(self.report_dir / "runs.jsonl")