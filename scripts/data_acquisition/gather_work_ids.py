"""
Command-line interface for the acquisition of the work IDs to load into the knowledge graph.

Gathers only the IDs (no metadata is downloaded); the output file is the input of the database population (scripts/data_load/populate_database.py)
and can be passed to the ETL pipeline with `src/etl_cli.py --work-ids-file`.

Examples (from the repository root):
    python scripts/data_acquisition/gather_work_ids.py -h                      # show help message
    python scripts/data_acquisition/gather_work_ids.py                         # seeds + topic + expansion, write data/work_ids.txt and data/work_ids_report.json
    python scripts/data_acquisition/gather_work_ids.py -m 2 -n 2 -o data/wide.txt  # looser expansion (links to at least 2 collected works), two rounds
    python scripts/data_acquisition/gather_work_ids.py --skip-webservice -x    # SPARQL only, no expansion (seeds and topic)
    python scripts/data_load/populate_database.py                                # set up the database and load the gathered documents
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data_acquisition.config import DEFAULT_MIN_LINKS, DEFAULT_ROUNDS  # noqa: E402
from scripts.data_acquisition.gatherer import GatherResult, WorkIdGatherer  # noqa: E402
from scripts.data_acquisition.work_ids import write_work_ids  # noqa: E402
from src.eurlex.webservice_api import WebserviceAPI  # noqa: E402
from src.utils.logging import configure_logging  # noqa: E402

LOGGER_NAME = "acquisition"


def gather_parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the work ID acquisition.

    Returns:
        Parsed command-line arguments as argparse.Namespace.
    """
    parser = argparse.ArgumentParser(
        description="Gather the Cellar work IDs of the documents to load into the knowledge graph."
    )

    parser.add_argument(
        "-o", "--output",
        dest="output",
        default=str(ROOT / "data" / "work_ids.txt"),
        help="Path of the file with the work IDs (default: data/work_ids.txt)"
    )
    parser.add_argument(
        "-r", "--report",
        dest="report",
        default=str(ROOT / "data" / "work_ids_report.json"),
        help="Path of the JSON report with provenance and statistics (default: data/work_ids_report.json)"
    )
    parser.add_argument(
        "-m", "--min-links",
        dest="min_links",
        type=int,
        default=DEFAULT_MIN_LINKS,
        help=f"Minimum number of collected works an expanded act has to be linked to (default: {DEFAULT_MIN_LINKS})"
    )
    parser.add_argument(
        "-n", "--rounds",
        dest="rounds",
        type=int,
        default=DEFAULT_ROUNDS,
        help=f"Number of expansion rounds (default: {DEFAULT_ROUNDS})"
    )
    parser.add_argument(
        "-x", "--no-expansion",
        action="store_true",
        dest="no_expansion",
        help="Do not expand the collection, keep only the seeds and the topic (default: false)"
    )
    parser.add_argument(
        "-w", "--skip-webservice",
        action="store_true",
        dest="skip_webservice",
        help="Do not use the EUR-Lex web service to cross-check the topic search (default: false)"
    )
    parser.add_argument(
        "-l", "--log-level",
        dest="log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )

    return parser.parse_args()


def build_report(
    result: GatherResult,
    min_links: int,
    rounds: int,
    webservice: bool
) -> dict:
    """
    Build the JSON report of a run: parameters, statistics and the provenance of every work.

    Args:
        result (GatherResult): The outcome of the acquisition.
        min_links (int): Minimum number of collected works an expanded act had to be linked to.
        rounds (int): Number of expansion rounds.
        webservice (bool): Whether the EUR-Lex web service was used.

    Returns:
        dict: The report, ready to be serialised to JSON.
    """
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parameters": {
            "min_links": min_links,
            "rounds": rounds,
            "webservice": webservice,
        },
        "stats": result.stats,
        "works": [
            {
                "work_id": work.work_id,
                "celex": work.celex,
                "stages": sorted(work.stages),
                "sources": sorted(work.sources),
                "links": work.links,
            }
            for work in sorted(result.works.values(), key=lambda w: w.celex or "")
        ],
    }


def acquire(
    output: Path,
    report: Path,
    min_links: int = DEFAULT_MIN_LINKS,
    rounds: int = DEFAULT_ROUNDS,
    use_webservice: bool = True
) -> GatherResult:
    """
    Gather the work IDs and write the ID list and the report; also used by scripts/data_load/populate_database.py.

    Args:
        output (Path): Path of the file with the work IDs.
        report (Path): Path of the JSON report.
        min_links (int): Minimum number of collected works an expanded act has to be linked to. Default 3.
        rounds (int): Number of expansion rounds; 0 disables the expansion. Default 1.
        use_webservice (bool): Cross-check the topic search with the EUR-Lex web service if its template is available. Default True.

    Returns:
        GatherResult: The collected works with provenance, and the statistics of the run.
    """
    webservice = None
    if use_webservice:
        try:
            webservice = WebserviceAPI()
        except FileNotFoundError as error:
            logging.getLogger(LOGGER_NAME).warning("web service not used: %s", error)

    result = WorkIdGatherer(webservice=webservice).gather(min_links=min_links, rounds=rounds)
    entries = [
        (work.work_id, f"{work.celex}  {'+'.join(sorted(work.stages))}")
        for work in sorted(result.works.values(), key=lambda w: w.celex or "")
    ]
    write_work_ids(output, entries)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(build_report(result, min_links, rounds, webservice is not None), indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> None:
    """Main entry point for the work ID acquisition CLI."""
    args = gather_parse_args()
    configure_logging(LOGGER_NAME, args.log_level)

    try:
        result = acquire(Path(args.output), Path(args.report), args.min_links, 0 if args.no_expansion else args.rounds, not args.skip_webservice)
    except Exception as error:
        print(f"Unexpected error: {error}")
        sys.exit(1)

    coherence = result.stats["coherence"]
    print(f"\nwork IDs: {len(result.works)} -> {args.output}")
    print(f"by stage: {result.stats['by_stage']}")
    print(f"links inside the collection: {coherence['edges']}, works without any: {len(coherence['isolated'])}")
    print(f"report: {args.report}")


if __name__ == "__main__":
    main()