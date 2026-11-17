"""
Statistics collected while the pipeline runs.

Every transformer step writes into a :class:`StepReport` (flat counters, grouped breakdowns, warnings). The pipeline
assembles them into a :class:`PipelineReport` that can be logged, written as JSON and aggregated over many documents.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


def _sorted_counter(
    counter: Counter
) -> dict[str, int]:
    """
    Convert a counter to a dictionary sorted by descending count, then by key.

    Args:
        counter (Counter): The counter to convert.

    Returns:
        dict[str, int]: The sorted counts.
    """
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0]))))


@dataclass
class StepReport:
    """
    Statistics of one transformer step.

    Attributes:
        name (str): Name of the step.
        triples_in (int): Number of triples entering the step.
        triples_out (int): Number of triples leaving the step.
        duration_s (float): Duration of the step in seconds.
        counters (Counter): Flat counters.
        breakdowns (dict[str, Counter]): Counters grouped by a named breakdown.
        warnings (list[str]): Warnings raised by the step.
    """
    name: str
    triples_in: int = 0
    triples_out: int = 0
    duration_s: float = 0.0
    counters: Counter = field(default_factory=Counter)
    breakdowns: dict[str, Counter] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def count(
        self,
        key: str,
        n: int = 1
    ) -> None:
        """
        Increase a flat counter (e.g. ``sameas_removed``).

        Args:
            key (str): Name of the counter.
            n (int): Amount to add; nothing happens when zero. Default 1.
        """
        if n:
            self.counters[key] += n

    def tally(
        self,
        group: str,
        key: str,
        n: int = 1
    ) -> None:
        """
        Increase a counter inside a named breakdown (e.g. group ``dropped_predicates``, key ``cdm:date``).

        Args:
            group (str): Name of the breakdown.
            key (str): Name of the counter inside the breakdown.
            n (int): Amount to add; nothing happens when zero. Default 1.
        """
        if n:
            self.breakdowns.setdefault(group, Counter())[key] += n

    def warn(
        self,
        message: str
    ) -> None:
        """
        Record a warning.

        Args:
            message (str): The warning text.
        """
        self.warnings.append(message)

    @property
    def triples_delta(self) -> int:
        """Change in the number of triples caused by the step."""
        return self.triples_out - self.triples_in

    def to_dict(
        self,
        top: Optional[int] = None
    ) -> dict[str, Any]:
        """
        Convert the report to a JSON-serializable dictionary.

        Args:
            top (Optional[int]): Keep only this many largest entries per breakdown; all if None. Default None.

        Returns:
            dict[str, Any]: The report as a dictionary.
        """
        def cut(
            c: Counter
        ) -> dict[str, int]:
            """
            Sort a counter and keep only the ``top`` largest entries.

            Args:
                c (Counter): The counter to cut.

            Returns:
                dict[str, int]: The sorted (and possibly truncated) counts.
            """
            d = _sorted_counter(c)
            return dict(list(d.items())[:top]) if top else d

        return {
            "name": self.name,
            "triples_in": self.triples_in,
            "triples_out": self.triples_out,
            "duration_s": round(self.duration_s, 3),
            "counters": _sorted_counter(self.counters),
            "breakdowns": {g: cut(c) for g, c in self.breakdowns.items()},
            "warnings": list(self.warnings),
        }


@dataclass
class TransformReport:
    """
    Statistics of the whole transformation.

    Attributes:
        steps (list[StepReport]): Reports of the executed steps, in order.
    """
    steps: list[StepReport] = field(default_factory=list)

    def begin(
        self,
        name: str,
        triples_in: int
    ) -> StepReport:
        """
        Start the report of a new step.

        Args:
            name (str): Name of the step.
            triples_in (int): Number of triples entering the step.

        Returns:
            StepReport: The new report, already appended to ``steps``.
        """
        step = StepReport(name=name, triples_in=triples_in)
        self.steps.append(step)
        return step

    @property
    def triples_in(self) -> int:
        """Number of triples entering the first step."""
        return self.steps[0].triples_in if self.steps else 0

    @property
    def triples_out(self) -> int:
        """Number of triples leaving the last step."""
        return self.steps[-1].triples_out if self.steps else 0

    @property
    def duration_s(self) -> float:
        """Total duration of all steps in seconds."""
        return sum(s.duration_s for s in self.steps)

    def step(
        self,
        name: str
    ) -> Optional[StepReport]:
        """
        Get the report of a step by its name.

        Args:
            name (str): Name of the step.

        Returns:
            Optional[StepReport]: The first matching report, or None if there is none.
        """
        return next((s for s in self.steps if s.name == name), None)

    def to_dict(
        self,
        top: Optional[int] = None
    ) -> dict[str, Any]:
        """
        Convert the report to a JSON-serializable dictionary.

        Args:
            top (Optional[int]): Keep only this many largest entries per breakdown; all if None. Default None.

        Returns:
            dict[str, Any]: The report as a dictionary.
        """
        return {
            "triples_in": self.triples_in,
            "triples_out": self.triples_out,
            "duration_s": round(self.duration_s, 3),
            "steps": [s.to_dict(top) for s in self.steps],
        }


@dataclass
class ExtractReport:
    """
    Statistics of the extract phase.

    Attributes:
        source (str): The extracted source.
        triples (int): Number of extracted triples.
        duration_s (float): Duration in seconds.
    """
    source: str = ""
    triples: int = 0
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the report to a JSON-serializable dictionary.

        Returns:
            dict[str, Any]: The report as a dictionary.
        """
        return {"source": self.source, "triples": self.triples, "duration_s": round(self.duration_s, 3)}


@dataclass
class LoadReport:
    """
    Statistics of the load phase (projection + database writes).

    Attributes:
        nodes_projected (int): Number of projected nodes.
        relationships_projected (int): Number of projected relationships.
        nodes_by_kind (Counter): Projected nodes per kind.
        relationships_by_type (Counter): Projected relationships per type.
        db_counters (Counter): Counters reported by the database (nodes_created, relationships_created, ...).
        batches (int): Number of database batches.
        duration_s (float): Duration in seconds.
        dry_run (bool): Whether nothing was written to the database.
        warnings (list[str]): Warnings raised while loading.
    """
    nodes_projected: int = 0
    relationships_projected: int = 0
    nodes_by_kind: Counter = field(default_factory=Counter)
    relationships_by_type: Counter = field(default_factory=Counter)
    db_counters: Counter = field(default_factory=Counter)  # nodes_created, relationships_created, properties_set ...
    batches: int = 0
    duration_s: float = 0.0
    dry_run: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the report to a JSON-serializable dictionary.

        Returns:
            dict[str, Any]: The report as a dictionary.
        """
        return {
            "nodes_projected": self.nodes_projected,
            "relationships_projected": self.relationships_projected,
            "nodes_by_kind": _sorted_counter(self.nodes_by_kind),
            "relationships_by_type": _sorted_counter(self.relationships_by_type),
            "db_counters": _sorted_counter(self.db_counters),
            "batches": self.batches,
            "duration_s": round(self.duration_s, 3),
            "dry_run": self.dry_run,
            "warnings": list(self.warnings),
        }


@dataclass
class PipelineReport:
    """
    Everything known about one document run.

    Attributes:
        source (str): The processed source.
        started_at (str): UTC start time in ISO format.
        extract (ExtractReport): Report of the extract phase.
        transform (TransformReport): Report of the transform phase.
        graph (dict[str, Any]): Summary of the canonical graph after the transformation.
        load (Optional[LoadReport]): Report of the load phase; None if nothing was loaded.
        duration_s (float): Total duration in seconds.
        error (Optional[str]): Error message if the run failed.
    """
    source: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    extract: ExtractReport = field(default_factory=ExtractReport)
    transform: TransformReport = field(default_factory=TransformReport)
    graph: dict[str, Any] = field(default_factory=dict)  # summary of the canonical graph after the transformation
    load: Optional[LoadReport] = None
    duration_s: float = 0.0
    error: Optional[str] = None

    def to_dict(
        self,
        top: Optional[int] = None
    ) -> dict[str, Any]:
        """
        Convert the report to a JSON-serializable dictionary.

        Args:
            top (Optional[int]): Keep only this many largest entries per breakdown; all if None. Default None.

        Returns:
            dict[str, Any]: The report as a dictionary.
        """
        return {
            "source": self.source,
            "started_at": self.started_at,
            "duration_s": round(self.duration_s, 3),
            "error": self.error,
            "extract": self.extract.to_dict(),
            "transform": self.transform.to_dict(top),
            "graph": self.graph,
            "load": self.load.to_dict() if self.load else None,
        }

    def to_json(
        self,
        top: Optional[int] = None
    ) -> str:
        """
        Serialize the report to indented JSON.

        Args:
            top (Optional[int]): Keep only this many largest entries per breakdown; all if None. Default None.

        Returns:
            str: The JSON text.
        """
        return json.dumps(self.to_dict(top), ensure_ascii=False, indent=2)

    def write_json(
        self,
        path: Path,
        top: Optional[int] = None
    ) -> Path:
        """
        Write the report as indented JSON, creating missing parent directories.

        Args:
            path (Path): The file to write.
            top (Optional[int]): Keep only this many largest entries per breakdown; all if None. Default None.

        Returns:
            Path: The written file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(top), encoding="utf-8")
        return path

    def append_jsonl(
        self,
        path: Path
    ) -> None:
        """
        Append the report as one compact line (one line per processed document).

        Args:
            path (Path): The JSON Lines file to append to.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")

    def summary_text(self) -> str:
        """
        Get a human-readable table for the console / thesis notes.

        Returns:
            str: The multi-line summary.
        """
        lines = [f"== {self.source}  ({self.duration_s:.1f} s){'  ERROR: ' + self.error if self.error else ''}"]
        lines.append(f"   extract : {self.extract.triples:>9,} triples  ({self.extract.duration_s:.1f} s)")
        for s in self.transform.steps:
            lines.append(f"   {s.name:<22}{s.triples_in:>9,} -> {s.triples_out:>9,}  ({s.triples_delta:+,})  {s.duration_s:.1f} s")
        if self.graph:
            lines.append(f"   graph   : {self.graph.get('nodes', 0):,} nodes, {self.graph.get('edges', 0):,} edges "
                         f"({self.graph.get('annotated_edges', 0):,} annotated)")
        if self.load:
            l = self.load
            lines.append(f"   load    : {l.nodes_projected:,} nodes, {l.relationships_projected:,} relationships"
                         f"{' (dry run)' if l.dry_run else ''}  {dict(l.db_counters) if l.db_counters else ''}")
        return "\n".join(lines)


def aggregate_reports(
    reports: Iterable[PipelineReport]
) -> dict[str, Any]:
    """
    Sum the statistics of several documents (per step: triples, counters, breakdowns) for reporting.

    Args:
        reports (Iterable[PipelineReport]): The per-document reports.

    Returns:
        dict[str, Any]: The summed statistics.
    """
    reports = list(reports)
    steps: dict[str, dict[str, Any]] = {}
    graph_nodes = Counter()
    graph_edges = Counter()
    load = Counter()
    for r in reports:
        for s in r.transform.steps:
            agg = steps.setdefault(s.name, {"triples_in": 0, "triples_out": 0, "duration_s": 0.0, "counters": Counter(), "breakdowns": {}})
            agg["triples_in"] += s.triples_in
            agg["triples_out"] += s.triples_out
            agg["duration_s"] += s.duration_s
            agg["counters"].update(s.counters)
            for g, c in s.breakdowns.items():
                agg["breakdowns"].setdefault(g, Counter()).update(c)
        graph_nodes.update(r.graph.get("nodes_by_kind", {}))
        graph_edges.update(r.graph.get("edges_by_type", {}))
        if r.load:
            load.update(r.load.db_counters)
            load["nodes_projected"] += r.load.nodes_projected
            load["relationships_projected"] += r.load.relationships_projected
    return {
        "documents": len(reports),
        "failed": [r.source for r in reports if r.error],
        "extracted_triples": sum(r.extract.triples for r in reports),
        "duration_s": round(sum(r.duration_s for r in reports), 3),
        "steps": {
            name: {
                "triples_in": a["triples_in"], "triples_out": a["triples_out"], "duration_s": round(a["duration_s"], 3),
                "counters": _sorted_counter(a["counters"]),
                "breakdowns": {g: _sorted_counter(c) for g, c in a["breakdowns"].items()},
            }
            for name, a in steps.items()
        },
        "graph_nodes_by_kind_summed": _sorted_counter(graph_nodes),
        "graph_edges_by_type_summed": _sorted_counter(graph_edges),
        "load_summed": _sorted_counter(load),
    }