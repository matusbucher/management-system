"""
Readable report (Markdown) of a database population run, rendered from the summary dictionary the run collects.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

_TOP_LABELS = 20  # the document types are labels, so there are dozens of them; the complete list is in summary.json


def render_summary(
    summary: Mapping[str, Any]
) -> str:
    """
    Render the summary of a population run as Markdown.

    Phases that did not run (because an earlier phase failed) are shown as not run.

    Args:
        summary (Mapping[str, Any]): The summary built by ``populate_database.py``.

    Returns:
        str: The Markdown document.
    """
    phases = summary.get("phases", {})
    lines = [
        "# Database population report",
        "",
        f"* Started: {summary.get('started_at')}, finished: {summary.get('finished_at', '-')}, duration: {_duration(summary.get('duration_s'))}",
        f"* Run directory: `{summary.get('run_dir')}`{' (resumed run)' if summary.get('resumed') else ''}",
        f"* Result: **{_result(summary)}** (exit code {summary.get('exit_code', '-')})",
    ]
    if summary.get("error"):
        lines.append(f"* Error: `{summary['error']}`")

    lines += ["", "## Phases", "", "| Phase | Status | Duration |", "| --- | --- | --- |"]
    for name in ("environment", "schema", "n10s", "ontology", "work_ids", "documents", "reconcile", "labels", "statistics"):
        record = phases.get(name)
        lines.append(f"| {name} | {record['status'] if record else 'not run'} | {_duration(record.get('duration_s')) if record else '-'} |")

    environment = phases.get("environment")
    if environment and "server" in environment:
        server = environment["server"]
        lines += [
            "", "## Environment", "",
            f"* Server: {server.get('name')} {server.get('version')} ({server.get('edition')})",
            f"* neosemantics (n10s): {environment.get('n10s')}; APOC: {environment.get('apoc') or 'not installed'}",
            f"* Before the run: {environment.get('nodes', 0):,} nodes, {environment.get('relationships', 0):,} relationships"
            + (f"; reset deleted {environment['reset']['nodes_deleted']:,} nodes" if environment.get("reset") else ""),
        ]

    ontology = phases.get("ontology")
    if ontology and "counts" in ontology:
        counts = ontology["counts"]
        lines += [
            "", "## CDM ontology", "",
            f"{'Imported now' if ontology.get('imported') else 'Already present'}: {counts['classes']:,} classes, "
            f"{counts['relationships']:,} relationships, {counts['properties']:,} properties.",
        ]
        for name, stats in ontology.get("files", {}).items():
            lines.append(f"* `{name}`: {stats['triples_loaded']:,} of {stats['triples_parsed']:,} triples loaded in {stats['duration_s']} s")

    work_ids = phases.get("work_ids")
    if work_ids and "listed" in work_ids:
        lines += ["", "## Work IDs", "", f"`{work_ids['file']}`: {work_ids['listed']:,} listed, {work_ids['selected']:,} selected for this run."]
        if work_ids.get("gathered"):
            lines.append(f"Gathered now: {work_ids['gathered']['works']:,} works, by stage {work_ids['gathered']['by_stage']}.")

    documents = phases.get("documents")
    if documents and "processed" in documents:
        seconds = documents["seconds"]
        lines += [
            "", "## Documents (this run)", "",
            "| | |", "| --- | --- |",
            f"| processed | {documents['processed']:,} |",
            f"| loaded without error | {documents['ok']:,} |",
            f"| failed | {documents['failed']:,} |",
            f"| skipped (loaded by a previous run) | {documents['skipped_already_loaded']:,} |",
            f"| extracted RDF triples | {documents['extracted_triples']:,} |",
            f"| projected nodes / relationships (before MERGE) | {documents['nodes_projected']:,} / {documents['relationships_projected']:,} |",
            f"| time: extract / transform / load / total | {_duration(seconds['extract'])} / {_duration(seconds['transform'])} / {_duration(seconds['load'])} / {_duration(seconds['total'])} |",
        ]
        if documents.get("database_counters"):
            lines += ["", "Changes made by the database writes:", ""]
            lines += _bullets(documents["database_counters"].items())
        if documents.get("slowest"):
            lines += ["", "Slowest documents:", ""]
            lines += [f"* `{d['work_id']}`: {d['duration_s']} s, {d['triples']:,} triples" for d in documents["slowest"]]
        if documents.get("failures"):
            lines += ["", "**Failures** (run again with `--resume` to retry them):", ""]
            lines += [f"* `{f['work_id']}`: {f['error']}" for f in documents["failures"]]
        lines.append("")
        lines.append("Per-step statistics summed over the documents are in `aggregate.json`, one report per document in `documents/`.")

    reconcile = phases.get("reconcile")
    if reconcile and reconcile.get("status") == "ok":
        lines += ["", "## Reconciliation", "", f"{reconcile.get('merged_nodes', 0):,} duplicated work nodes merged."]
        lines += [f"* warning: {w}" for w in reconcile.get("warnings", [])]

    labels = phases.get("labels")
    if labels and labels.get("status") == "ok":
        lines += ["", "## Labels of reference data", "",
                  f"{labels['labelled']:,} of {labels['missing']:,} concepts and institutions got an English label, {labels['unresolved']:,} have none in the SPARQL endpoint."]

    statistics = phases.get("statistics")
    if statistics and "nodes_by_label" in statistics:
        lines += ["", "## Database after the run", "",
                  f"{statistics['nodes']:,} nodes and {statistics['relationships']:,} relationships (the ontology is not counted).",
                  f"Works: {statistics['works'].get('loaded', 0):,} with their own metadata (the requested works and works the downloaded dumps describe), "
                  f"{statistics['works'].get('stub', 0):,} stubs (known only as the end of a relation).",
                  f"Works stored twice under different identifiers (same CELEX number): {statistics['works_duplicated_by_celex']:,}."]
        requested = statistics.get("requested_works")
        if requested:
            lines.append(f"Requested works present in the database: {requested['present']:,} of {requested['listed']:,}.")
        labels = list(statistics["nodes_by_label"].items())
        lines += ["", f"Nodes by label (the {_TOP_LABELS} largest of {len(labels)}):", ""] + _bullets(labels[:_TOP_LABELS])
        lines += ["", "Relationships by type:", ""] + _bullets(statistics["relationships_by_type"].items())
        if statistics.get("most_connected_works"):
            lines += ["", "Most connected works:", ""]
            lines += [f"* {w['celex'] or w['uri']}: {w['degree']:,} relationships" for w in statistics["most_connected_works"]]
    lines.append("")
    return "\n".join(lines)


def _result(
    summary: Mapping[str, Any]
) -> str:
    """
    Describe the outcome of the run in a word.

    Args:
        summary (Mapping[str, Any]): The summary of the run.

    Returns:
        str: ``completed``, ``completed with failed documents``, ``interrupted`` or ``failed``.
    """
    code = summary.get("exit_code")
    return {0: "completed", 1: "completed with failed documents", 130: "interrupted"}.get(code, "failed")


def _bullets(
    items: Iterable[tuple[str, int]]
) -> list[str]:
    """
    Format name/count pairs as Markdown bullets.

    Args:
        items (Iterable[tuple[str, int]]): The pairs.

    Returns:
        list[str]: One bullet per pair.
    """
    return [f"* {name}: {count:,}" for name, count in items]


def _duration(
    seconds: Any
) -> str:
    """
    Format a number of seconds as ``h:mm:ss`` (or seconds with one decimal below a minute).

    Args:
        seconds (Any): The duration in seconds, or None.

    Returns:
        str: The formatted duration, ``-`` if unknown.
    """
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds:.1f} s"
    whole = int(seconds)
    return f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"
