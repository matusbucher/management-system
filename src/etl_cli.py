"""
Command-line runner of the ETL pipeline.

Examples (from the repository root):
    python src/etl_cli.py data                                  # transform every data/*.rdf, project to nodes/edges, no database
    python src/etl_cli.py data/NIS2.rdf --log-level DEBUG       # one file, full per-step breakdowns in the log
    python src/etl_cli.py data --load --password secret         # write to Neo4j
    python src/etl_cli.py --work-id 0caf473a-85bd-11ed-9887-01aa75ed71a1 --load
Reports are written to --report-dir (one JSON per document, runs.jsonl and aggregate.json).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.etlpipe.neo4j_database import Neo4jDatabase

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOGGER_NAME = "etlpipe"

from src.etlpipe.neo4j_database import NEO4J_DEFAULT_HOST, NEO4J_DEFAULT_PASSWORD, NEO4J_DEFAULT_PORT, NEO4J_DEFAULT_USER  # noqa: E402
from src.etlpipe.context import ALL_CATEGORIES, DEFAULT_CATEGORIES, CanonicalScheme, Category, TransformOptions  # noqa: E402
from src.etlpipe.extractor import CellarExtractor, FileExtractor  # noqa: E402
from src.etlpipe.loader import Neo4jLoader  # noqa: E402
from utils.logging import configure_logging  # noqa: E402
from src.etlpipe.pipeline import EtlPipeline  # noqa: E402
from src.etlpipe.transformer import TransformerChain  # noqa: E402
from src.etlpipe.constants import WEMILevel  # noqa: E402


def parse_args(
    argv: Optional[list[str]] = None
) -> argparse.Namespace:
    """
    Parse command-line arguments of the ETL runner.

    Args:
        argv (Optional[list[str]]): Arguments to parse. Default None (read ``sys.argv``).

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    p = argparse.ArgumentParser(description="Run the ETL pipeline: RDF metadata -> canonical work graph -> Neo4j.")
    p.add_argument("inputs", nargs="*", type=Path, help="RDF/XML files or directories containing *.rdf files")
    p.add_argument("--work-id", action="append", default=[], metavar="UUID", help="fetch this Cellar work from the API (repeatable)")
    p.add_argument("--load", action="store_true", help="write to Neo4j (default: transform and project only)")
    p.add_argument("--report-dir", type=Path, default=ROOT / "tmp" / "etl_reports", help="where to write the statistics reports")
    p.add_argument("--snapshot-dir", type=Path, help="serialise the graph after every step (Turtle) for inspection")
    p.add_argument("--top", type=int, help="keep only the N largest entries of each breakdown in the reports")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.add_argument("--log-file", type=Path)
    opt = p.add_argument_group("transformer options")
    opt.add_argument("--wemi-levels", default="work", help="comma separated: work,expression,manifestation,item (default: work)")
    opt.add_argument("--categories", default=",".join(sorted([category.value for category in DEFAULT_CATEGORIES])),
                     help=f"relation categories to keep, from: {','.join(sorted([category.value for category in ALL_CATEGORIES]))}")
    opt.add_argument("--lifecycle", action="store_true",
                     help="track the document lifecycle: load dossiers (procedures) and their events (shortcut for adding the 'lifecycle' category)")
    opt.add_argument("--canonical-scheme", default="celex", choices=["celex", "cellar"])
    opt.add_argument("--citation-sources", help="only these source kinds may cite (e.g. legislation,consolidated); default: all")
    db = p.add_argument_group("neo4j (with --load)")
    db.add_argument("--host", default=NEO4J_DEFAULT_HOST)
    db.add_argument("--port", type=int, default=NEO4J_DEFAULT_PORT)
    db.add_argument("--user", default=NEO4J_DEFAULT_USER)
    db.add_argument("--password", default=NEO4J_DEFAULT_PASSWORD)
    db.add_argument("--reconcile-aliases", action="store_true", help="merge duplicate works after loading (needs APOC)")
    return p.parse_args(argv)


def collect_files(
    inputs: list[Path]
) -> list[Path]:
    """
    Expand the input paths into a list of RDF files (directories contribute their ``*.rdf`` files).

    Args:
        inputs (list[Path]): Files or directories given on the command line.

    Returns:
        list[Path]: The RDF files to process.
    """
    files: list[Path] = []
    for path in inputs:
        files.extend(sorted(path.glob("*.rdf")) if path.is_dir() else [path])
    return files


def build_options(
    args: argparse.Namespace
) -> TransformOptions:
    """
    Build the transformer options from the parsed command-line arguments.

    Args:
        args (argparse.Namespace): Parsed command-line arguments.

    Returns:
        TransformOptions: Options for the transformer chain.
    """
    categories = {Category(c.strip()) for c in args.categories.split(",") if c.strip()}
    if args.lifecycle:
        categories.add(Category.LIFECYCLE)
    return TransformOptions(
        wemi_levels=frozenset(WEMILevel(v.strip()) for v in args.wemi_levels.split(",") if v.strip()),
        include_categories=frozenset(categories),
        canonical_scheme=CanonicalScheme(args.canonical_scheme),
        citation_source_kinds=frozenset(k.strip() for k in args.citation_sources.split(",")) if args.citation_sources else None,
    )


def main(
    argv: Optional[list[str]] = None
) -> int:
    """
    Run the ETL pipeline on the given files and/or Cellar works and print the reports.

    Args:
        argv (Optional[list[str]]): Command-line arguments. Default None (read ``sys.argv``).

    Returns:
        int: Exit code - 0 on success, 1 if any document failed, 2 if there was nothing to do.
    """
    args = parse_args(argv)
    configure_logging(LOGGER_NAME, args.log_level, args.log_file)
    files = collect_files(args.inputs)
    if not files and not args.work_id:
        print("nothing to do: give RDF files/directories or --work-id", file=sys.stderr)
        return 2

    db: Optional[Neo4jDatabase] = None
    if args.load:
        from src.etlpipe.neo4j_database import Neo4jDatabase
        db = Neo4jDatabase(args.host, args.port, args.user, args.password)
        db.verify_connection()
    loader = Neo4jLoader(db, reconcile_aliases=args.reconcile_aliases)
    options = build_options(args)
    chain = TransformerChain.default_chain(snapshot_dir=args.snapshot_dir)

    reports = []
    pipelines = []
    try:
        if files:
            pipelines.append(EtlPipeline(FileExtractor(), chain, loader, options, args.report_dir, args.top))
            reports += pipelines[-1].run_many(files, dry_run=not args.load)
        if args.work_id:
            from src.eurlex.cellar_api import CellarPS, CellarResourceId
            pipelines.append(EtlPipeline(CellarExtractor(), chain, loader, options, args.report_dir, args.top))
            reports += pipelines[-1].run_many([CellarResourceId(CellarPS.CELLAR, w) for w in args.work_id], dry_run=not args.load)
    finally:
        if db is not None:
            db.close()

    pipelines[0].write_aggregate(reports)
    for report in reports:
        print(report.summary_text())
    print(f"\nreports: {args.report_dir}")
    return 1 if any(r.error for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
