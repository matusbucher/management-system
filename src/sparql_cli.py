"""
Command-line interface for the Publications Office SPARQL endpoint wrapper.

Examples (from the repository root):
    python src/sparql_cli.py -h                                                                     # show help message
    python src/sparql_cli.py -q "SELECT ?s WHERE { ?s ?p ?o } LIMIT 5"                              # run a query and print the response (JSON)
    python src/sparql_cli.py -i query.rq -f csv -o result.csv                                       # run a query from a file and save the CSV response
    python src/sparql_cli.py -q "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o } LIMIT 5" -f turtle       # run a CONSTRUCT query and print the RDF in Turtle
"""

import argparse

from pathlib import Path
from urllib.error import HTTPError, URLError

from eurlex.sparql_api import SparqlAPI, SparqlFormat
from utils.parse_input import get_str_value


def sparql_parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the Publications Office SPARQL endpoint wrapper.

    Returns:
        Parsed command-line arguments as argparse.Namespace.
    """
    parser = argparse.ArgumentParser(
        description="Wrapper for calling the Publications Office SPARQL endpoint."
    )

    parser.add_argument(
        "-i", "--input-query",
        dest="input_query",
        help="Path to a file with the SPARQL query to send"
    )
    parser.add_argument(
        "-q", "--query",
        dest="query",
        help="SPARQL query string"
    )
    parser.add_argument(
        "-f", "--format",
        choices=[response_format.name.lower() for response_format in SparqlFormat],
        default="json",
        dest="format",
        help="Format of the response (default: json)"
    )
    parser.add_argument(
        "-o", "--output",
        dest="output",
        help="Optional path where the response should be saved"
    )
    parser.add_argument(
        "-e", "--endpoint",
        dest="endpoint",
        help="SPARQL endpoint URL (default: http://publications.europa.eu/webapi/rdf/sparql)"
    )
    parser.add_argument(
        "-r", "--rows-only",
        action="store_true",
        dest="rows_only",
        help="Print only the result rows of a SELECT query, one per line (works with the json format)"
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point for the SPARQL API CLI."""
    args = sparql_parse_args()

    if args.input_query:
        query_path = Path(args.input_query)
        if not query_path.exists():
            print(f"Query file not found: {query_path}")
            return
        query = query_path.read_text(encoding="utf-8")
    else:
        query = get_str_value(args.query, "SPARQL query", default=None)

    response_format = SparqlFormat[args.format.upper()]
    sparql = SparqlAPI(args.endpoint) if args.endpoint else SparqlAPI()

    if args.rows_only and response_format != SparqlFormat.JSON:
        print("Option --rows-only requires the json format.")
        return

    try:
        response = sparql.execute(query, response_format)
        if args.output:
            Path(args.output).write_text(response, encoding="utf-8")
            print(f"Response saved to: {args.output}")
        elif args.rows_only:
            rows = SparqlAPI.parse_bindings(response)
            if rows:
                for row in rows:
                    print("\t".join(f"{variable}={value}" for variable, value in row.items()))
            else:
                print("No result rows found in response.")
        else:
            print("\n--- SPARQL Response ---")
            print(response)
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        print(f"HTTP error: {error.code} {error.reason}")
        print("\n--- Error response body ---")
        print(error_body)
    except URLError as error:
        print(f"Connection error: {error.reason}")
    except Exception as error:
        print(f"Unexpected error: {error}")


if __name__ == "__main__":
    main()
