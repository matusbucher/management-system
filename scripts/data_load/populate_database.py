"""
Populate the Neo4j database of the knowledge graph from scratch (or continue an interrupted population).

The process, every phase logged and timed (see docs/DATABASE_POPULATION.md):
    1. environment   check the server and the n10s / APOC plugins
    2. schema        constraint and indexes of the graph (the ones the loader relies on)
    3. n10s          neosemantics graph configuration
    4. ontology      import of the CDM ontology with n10s
    5. work IDs      read the list from data/work_ids.txt (or gather it first with --refresh-ids)
    6. documents     for every work: download metadata from Cellar, transform, load (one report per document)
    7. reconcile     merge works that exist twice under different identifiers (needs APOC)
    8. labels        English labels of EuroVoc concepts and authority table entries (SPARQL)
    9. statistics    what is in the database; summary.md / summary.json

Examples (from the repository root; the database has to be running):
    python scripts/data_load/populate_database.py -h                            # show help message
    python scripts/data_load/populate_database.py --limit 3                     # try the whole process on the first 3 works of the list
    python scripts/data_load/populate_database.py                               # populate with data/work_ids.txt
    python scripts/data_load/populate_database.py --resume data/population/20261118-091500   # continue an interrupted run
    python scripts/data_load/populate_database.py --reset --yes                 # delete everything in the database first
    python scripts/data_load/populate_database.py --refresh-ids                 # gather the work IDs again before loading
Reports are written to data/population/<time of the run>/ (populate.log, summary.md, summary.json, aggregate.json, documents/).
"""

import argparse
import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data_acquisition.gather_work_ids import acquire  # noqa: E402
from scripts.data_load.database_setup import DEFAULT_ONTOLOGY_FILES, DatabaseSetup  # noqa: E402
from scripts.data_load.summary import render_summary  # noqa: E402
from src.etlpipe.constants import WEMILevel  # noqa: E402
from src.etlpipe.context import DEFAULT_CATEGORIES, Category, TransformOptions  # noqa: E402
from src.etlpipe.extractor import CellarExtractor  # noqa: E402
from src.etlpipe.loader import Neo4jLoader  # noqa: E402
from src.etlpipe.neo4j_database import NEO4J_DEFAULT_HOST, NEO4J_DEFAULT_PASSWORD, NEO4J_DEFAULT_PORT, NEO4J_DEFAULT_USER, Neo4jDatabase  # noqa: E402
from src.etlpipe.pipeline import EtlPipeline  # noqa: E402
from src.etlpipe.report import LoadReport, PipelineReport, aggregate_reports  # noqa: E402
from src.etlpipe.transformer import TransformerChain  # noqa: E402
from src.etlpipe.work_ids import read_work_ids  # noqa: E402
from src.eurlex.cellar_api import CellarPS, CellarResourceId  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402

LOGGER_NAME = "etlpipe.populate"
DEFAULT_WORK_IDS_FILE = ROOT / "data" / "work_ids.txt"
DEFAULT_RUNS_DIR = ROOT / "data" / "population"

EXIT_OK = 0
EXIT_DOCUMENT_FAILED = 1
EXIT_BAD_USAGE = 2
EXIT_INTERRUPTED = 130

logger = logging.getLogger(LOGGER_NAME)


def populate_parse_args(
    argv: Optional[list[str]] = None
) -> argparse.Namespace:
    """
    Parse command-line arguments for the database population.

    Args:
        argv (Optional[list[str]]): Arguments to parse. Default None (read ``sys.argv``).

    Returns:
        Parsed command-line arguments as argparse.Namespace.
    """
    parser = argparse.ArgumentParser(
        description="Populate the Neo4j database of the knowledge graph: schema, n10s, CDM ontology, documents, labels, statistics."
    )

    parser.add_argument(
        "-w", "--work-ids-file",
        dest="work_ids_file",
        type=Path,
        default=DEFAULT_WORK_IDS_FILE,
        help="File with the Cellar work IDs to load (default: data/work_ids.txt)"
    )
    parser.add_argument(
        "-r", "--refresh-ids",
        action="store_true",
        dest="refresh_ids",
        help="Gather the work IDs again (scripts/data_acquisition) and overwrite the file before loading (default: false)"
    )
    parser.add_argument(
        "-n", "--limit",
        dest="limit",
        type=int,
        help="Load only the first N works of the list (to try the process)"
    )
    parser.add_argument(
        "--resume",
        dest="resume",
        type=Path,
        metavar="RUN_DIR",
        help="Continue the run in this directory: works with a successful report there are skipped"
    )
    parser.add_argument(
        "--run-dir",
        dest="run_dir",
        type=Path,
        help="Directory for the logs and reports (default: data/population/<time of the run>)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        dest="reset",
        help="Delete all nodes and the n10s configuration before populating (needs --yes)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        dest="yes",
        help="Confirm the destructive --reset"
    )
    parser.add_argument(
        "--no-lifecycle",
        action="store_true",
        dest="no_lifecycle",
        help="Do not load the document lifecycle (dossiers and events); loaded by default"
    )
    parser.add_argument(
        "--skip-ontology",
        action="store_true",
        dest="skip_ontology",
        help="Do not import the CDM ontology"
    )
    parser.add_argument(
        "--ontology-files",
        dest="ontology_files",
        default=",".join(DEFAULT_ONTOLOGY_FILES),
        help="Comma separated CDM files in data/cdm to import (default: cdm.rdf)"
    )
    parser.add_argument(
        "--skip-labels",
        action="store_true",
        dest="skip_labels",
        help="Do not fetch the labels of concepts and institutions"
    )
    parser.add_argument(
        "--no-reconcile",
        action="store_true",
        dest="no_reconcile",
        help="Do not merge duplicated works after loading (done only if APOC is installed)"
    )
    parser.add_argument(
        "--top",
        dest="top",
        type=int,
        default=50,
        help="Keep only the N largest entries of each breakdown in the per-document reports (default: 50)"
    )
    parser.add_argument(
        "-l", "--log-level",
        dest="log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    database = parser.add_argument_group("neo4j")
    database.add_argument("--host", default=NEO4J_DEFAULT_HOST)
    database.add_argument("--port", type=int, default=NEO4J_DEFAULT_PORT)
    database.add_argument("--user", default=NEO4J_DEFAULT_USER)
    database.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", NEO4J_DEFAULT_PASSWORD), help="default: $NEO4J_PASSWORD or the project default")

    return parser.parse_args(argv)


@contextmanager
def phase(
    summary: dict[str, Any],
    name: str,
    number: int,
    total: int
) -> Iterator[dict[str, Any]]:
    """
    Log and time one phase of the population and record it in the summary.

    The phase record (``status``, ``duration_s`` and whatever the body puts into the yielded dictionary) is stored in
    ``summary["phases"][name]`` even if the body raises.

    Args:
        summary (dict[str, Any]): The summary of the run.
        name (str): The name of the phase.
        number (int): The number of the phase, for the log.
        total (int): The total number of phases, for the log.

    Yields:
        dict[str, Any]: The record of the phase, to be filled by the body.
    """
    record: dict[str, Any] = {"status": "running"}
    summary["phases"][name] = record
    logger.info("phase %d/%d: %s", number, total, name)
    started = time.perf_counter()
    try:
        yield record
        if record["status"] == "running":
            record["status"] = "ok"
    except BaseException as exc:
        record["status"] = "failed" if isinstance(exc, Exception) else "interrupted"
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        record["duration_s"] = round(time.perf_counter() - started, 2)
        logger.info("phase %d/%d: %s %s in %.1fs", number, total, name, record["status"], record["duration_s"])


def previous_successes(
    documents_dir: Path
) -> set[str]:
    """
    Find the works that a previous run in the directory loaded successfully.

    Args:
        documents_dir: The ``documents`` directory of the run.

    Returns:
        set[str]: Work IDs whose report exists and has no error.
    """
    done: set[str] = set()
    for path in documents_dir.glob("*.json"):
        if path.name == "aggregate.json":
            continue
        try:
            if not json.loads(path.read_text(encoding="utf-8")).get("error"):
                done.add(path.stem)
        except (OSError, ValueError):
            continue
    return done


def load_documents(
    work_ids: list[str],
    pipeline: EtlPipeline,
    skip: set[str]
) -> tuple[list[PipelineReport], list[str], bool]:
    """
    Run the pipeline for every work with progress and time estimate in the log.

    Args:
        work_ids (list[str]): The works to load.
        pipeline (EtlPipeline): The pipeline (Cellar extractor, transformer chain, Neo4j loader).
        skip (set[str]): Works to skip because a previous run loaded them.

    Returns:
        tuple[list[PipelineReport], list[str], bool]: The reports of the processed works, the skipped works and whether
            the run was interrupted.
    """
    todo = [work_id for work_id in work_ids if work_id not in skip]
    skipped = [work_id for work_id in work_ids if work_id in skip]
    if skipped:
        logger.info("documents: %d works already loaded by the previous run are skipped", len(skipped))
    reports: list[PipelineReport] = []
    started = time.perf_counter()
    try:
        for index, work_id in enumerate(todo, start=1):
            report = pipeline.run(CellarResourceId(CellarPS.CELLAR, work_id), name=work_id)
            reports.append(report)
            elapsed = time.perf_counter() - started
            eta = elapsed / index * (len(todo) - index)
            logger.info(
                "documents [%d/%d] %s %s in %.1fs (%s nodes, %s relationships) - elapsed %s, remaining about %s",
                index, len(todo), work_id, f"FAILED: {report.error}" if report.error else "ok", report.duration_s,
                f"{report.load.nodes_projected:,}" if report.load else "-", f"{report.load.relationships_projected:,}" if report.load else "-",
                timedelta(seconds=int(elapsed)), timedelta(seconds=int(eta)),
            )
    except KeyboardInterrupt:
        logger.warning("documents: interrupted after %d of %d works; continue with --resume", len(reports), len(todo))
        return reports, skipped, True
    return reports, skipped, False


def document_statistics(
    reports: list[PipelineReport],
    skipped: list[str]
) -> dict[str, Any]:
    """
    Aggregate the per-document reports into the headline statistics of the loading phase.

    Args:
        reports (list[PipelineReport]): The reports of the works processed in this run.
        skipped (list[str]): The works skipped because a previous run loaded them.

    Returns:
        dict[str, Any]: Counts, totals, time per stage, the slowest documents and the failures.
    """
    ok = [r for r in reports if not r.error]
    failed = [r for r in reports if r.error]
    db_counters: dict[str, int] = {}
    for report in ok:
        if report.load:
            for key, value in report.load.db_counters.items():
                db_counters[key] = db_counters.get(key, 0) + value
    return {
        "processed": len(reports),
        "ok": len(ok),
        "failed": len(failed),
        "skipped_already_loaded": len(skipped),
        "extracted_triples": sum(r.extract.triples for r in reports),
        "nodes_projected": sum(r.load.nodes_projected for r in ok if r.load),
        "relationships_projected": sum(r.load.relationships_projected for r in ok if r.load),
        "database_counters": dict(sorted(db_counters.items())),
        "seconds": {
            "extract": round(sum(r.extract.duration_s for r in reports), 1),
            "transform": round(sum(r.transform.duration_s for r in reports), 1),
            "load": round(sum(r.load.duration_s for r in ok if r.load), 1),
            "total": round(sum(r.duration_s for r in reports), 1),
        },
        "slowest": [{"work_id": r.source, "duration_s": round(r.duration_s, 1), "triples": r.extract.triples}
                    for r in sorted(reports, key=lambda r: -r.duration_s)[:5]],
        "failures": [{"work_id": r.source, "error": r.error} for r in failed],
    }


def build_pipeline(
    db: Neo4jDatabase,
    run_dir: Path,
    lifecycle: bool,
    top: Optional[int]
) -> tuple[EtlPipeline, Neo4jLoader]:
    """
    Assemble the ETL pipeline that loads works from Cellar into the database.

    Args:
        db (Neo4jDatabase): The database wrapper.
        run_dir (Path): The directory of the run; the per-document reports go to its ``documents`` subdirectory.
        lifecycle (bool): Whether to load the document lifecycle (dossiers and events).
        top (Optional[int]): Number of the largest entries of each breakdown kept in the per-document reports.

    Returns:
        tuple[EtlPipeline, Neo4jLoader]: The pipeline and its loader.
    """
    categories = DEFAULT_CATEGORIES | {Category.LIFECYCLE} if lifecycle else DEFAULT_CATEGORIES
    options = TransformOptions(wemi_levels=frozenset({WEMILevel.WORK}), include_categories=frozenset(categories))
    loader = Neo4jLoader(db)
    pipeline = EtlPipeline(CellarExtractor(), TransformerChain.default_chain(), loader, options, run_dir / "documents", top)
    return pipeline, loader


def write_summary(
    run_dir: Path,
    summary: dict[str, Any]
) -> None:
    """
    Write ``summary.json`` and the readable ``summary.md`` of the run.

    Args:
        run_dir (Path): The directory of the run.
        summary (dict[str, Any]): The summary of the run.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    previous = run_dir / "previous_summaries"
    for old in (run_dir / "summary.json", run_dir / "summary.md"):
        if old.exists():  # a resumed run reports only its own work, so the summaries of the earlier invocations are kept
            previous.mkdir(exist_ok=True)
            stamp = datetime.fromtimestamp(old.stat().st_mtime).strftime("%Y%m%d-%H%M%S")
            old.replace(previous / f"{old.stem}-{stamp}{old.suffix}")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (run_dir / "summary.md").write_text(render_summary(summary), encoding="utf-8")


def main(
    argv: Optional[list[str]] = None
) -> int:
    """
    Run the whole population process.

    Args:
        argv (Optional[list[str]]): Command-line arguments. Default None (read ``sys.argv``).

    Returns:
        int: Exit code - 0 on success, 1 if any document failed, 2 on a usage or environment error, 130 if interrupted.
    """
    args = populate_parse_args(argv)
    if args.reset and not args.yes:
        print("--reset deletes everything in the database: add --yes to confirm", file=sys.stderr)
        return EXIT_BAD_USAGE

    started_at = datetime.now(timezone.utc)
    run_dir = args.resume or args.run_dir or DEFAULT_RUNS_DIR / started_at.astimezone().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ("etlpipe", "acquisition"):
        configure_logging(name, args.log_level, run_dir / "populate.log")
    logging.getLogger("neo4j").setLevel(logging.ERROR)  # the driver warns about every query that uses a property that does not exist yet
    logger.info("run directory: %s", run_dir)

    summary: dict[str, Any] = {
        "started_at": started_at.isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "resumed": bool(args.resume),
        "parameters": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items() if k != "password"},
        "phases": {},
    }
    total = 9
    exit_code = EXIT_OK
    db: Optional[Neo4jDatabase] = None
    try:
        with phase(summary, "environment", 1, total) as record:
            db = Neo4jDatabase(args.host, args.port, args.user, args.password)
            db.verify_connection()
            setup = DatabaseSetup(db)
            environment = setup.check_environment()
            record.update(environment)
            logger.info("environment: %s %s %s, n10s %s, APOC %s; %d nodes and %d relationships in the database",
                        environment["server"]["name"], environment["server"]["version"], environment["server"]["edition"],
                        environment["n10s"], environment["apoc"] or "not installed", environment["nodes"], environment["relationships"])
            if args.reset:
                record["reset"] = setup.reset()
                logger.warning("environment: database reset, %d nodes deleted", record["reset"]["nodes_deleted"])

        with phase(summary, "schema", 2, total) as record:
            record["constraints_and_indexes"] = setup.ensure_schema()

        with phase(summary, "n10s", 3, total) as record:
            record["created"] = setup.configure_n10s()
            logger.info("n10s: graph configuration %s", "created" if record["created"] else "already present")

        with phase(summary, "ontology", 4, total) as record:
            if args.skip_ontology:
                record["status"] = "skipped"
            else:
                record.update(setup.import_ontology([name.strip() for name in args.ontology_files.split(",") if name.strip()]))
                logger.info("ontology: %s, %s", "imported" if record["imported"] else "already present", record["counts"])

        with phase(summary, "work_ids", 5, total) as record:
            if args.refresh_ids or not args.work_ids_file.exists():
                logger.info("work IDs: gathering them (%s)", "requested" if args.refresh_ids else f"{args.work_ids_file} does not exist")
                result = acquire(args.work_ids_file, args.work_ids_file.with_name(args.work_ids_file.stem + "_report.json"))
                record["gathered"] = {"works": len(result.works), "by_stage": result.stats["by_stage"]}
            work_ids = read_work_ids(args.work_ids_file)
            record["file"] = str(args.work_ids_file)
            record["listed"] = len(work_ids)
            if args.limit:
                work_ids = work_ids[:args.limit]
            record["selected"] = len(work_ids)
            logger.info("work IDs: %d listed, %d selected", record["listed"], record["selected"])

        pipeline, loader = build_pipeline(db, run_dir, not args.no_lifecycle, args.top)
        skip = previous_successes(run_dir / "documents") if args.resume else set()
        reports: list[PipelineReport] = []
        interrupted = False
        with phase(summary, "documents", 6, total) as record:
            reports, skipped, interrupted = load_documents(work_ids, pipeline, skip)
            record.update(document_statistics(reports, skipped))
            if interrupted:
                record["status"] = "interrupted"
            if reports:
                (run_dir / "aggregate.json").write_text(json.dumps(aggregate_reports(reports), ensure_ascii=False, indent=2), encoding="utf-8")
            if record["failed"]:
                exit_code = EXIT_DOCUMENT_FAILED
                logger.error("documents: %d of %d works failed: %s", record["failed"], record["processed"], [f["work_id"] for f in record["failures"]])

        with phase(summary, "reconcile", 7, total) as record:
            if args.no_reconcile or interrupted or summary["phases"]["environment"]["apoc"] is None:
                record["status"] = "skipped"
                if summary["phases"]["environment"]["apoc"] is None:
                    logger.info("reconcile: skipped, APOC is not installed (duplicates are counted in the statistics)")
            else:
                report = LoadReport()
                loader.reconcile(report)
                record["merged_nodes"] = report.db_counters.get("nodes_merged", 0)
                record["warnings"] = report.warnings

        with phase(summary, "labels", 8, total) as record:
            if args.skip_labels or interrupted:
                record["status"] = "skipped"
            else:
                record.update(setup.enrich_labels())
                logger.info("labels: %s", {k: record[k] for k in ("missing", "labelled", "unresolved")})

        with phase(summary, "statistics", 9, total) as record:
            record.update(setup.statistics(work_ids))
            logger.info("statistics: %d nodes, %d relationships; works %s", record["nodes"], record["relationships"], record["works"])

        if interrupted:
            exit_code = EXIT_INTERRUPTED
    except KeyboardInterrupt:
        logger.warning("interrupted")
        exit_code = EXIT_INTERRUPTED
    except Exception as exc:
        logger.exception("the population failed")
        summary["error"] = f"{type(exc).__name__}: {exc}"
        exit_code = EXIT_BAD_USAGE
    finally:
        if db is not None:
            db.close()
        summary["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        summary["duration_s"] = round((datetime.now(timezone.utc) - started_at).total_seconds(), 1)
        summary["exit_code"] = exit_code
        write_summary(run_dir, summary)
        logger.info("summary written to %s", run_dir / "summary.md")
        print(f"\nreports: {run_dir}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
