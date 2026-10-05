import argparse

from pathlib import Path
from urllib.error import HTTPError, URLError

from .etl.webservice_api import WebserviceAPI
from .etl.utils import get_int_value, get_str_value


def webservice_parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the EUR-Lex SOAP web service wrapper.
    
    Returns:
        Parsed command-line arguments as argparse.Namespace.
    """
    parser = argparse.ArgumentParser(
        description="Wrapper for calling the EUR-Lex SOAP web service."
    )

    parser.add_argument(
        "-i", "--input-request",
        dest="input_request",
        help="Path to a SOAP XML request file to send directly"
    )
    parser.add_argument(
        "-o", "--save-request",
        dest="save_request",
        help="Optional path where the request XML should be saved"
    )
    parser.add_argument(
        "-q", "--query",
        dest="query",
        help="Expert query string for the search request"
    )
    parser.add_argument(
        "-p", "--page",
        help="Page index in the search results (default: 1)"
    )
    parser.add_argument(
        "-s", "--page-size",
        dest="page_size",
        help="Page size for the search results (default: 1)"
    )
    parser.add_argument(
        "-l", "--language",
        dest="language",
        help="Search language (default: en)"
    )
    parser.add_argument(
        "-e", "--exclude-consleg",
        dest="exclude_consleg",
        action="store_true",
        help="Exclude all consolidated legislation (default: false)"
    )
    parser.add_argument(
        "-t", "--latest-consleg",
        dest="latest_consleg",
        action="store_true",
        help="Limit to the latest consolidated legislation (default: false)"
    )
    parser.add_argument(
        "-a", "--available-in",
        dest="available_in",
        help="Limit to documents in specific languages"
    )
    parser.add_argument(
        "-r", "--references-only",
        dest="references_only",
        action="store_true",
        help="Print only reference IDs from the SOAP response"
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point for the Webservice API CLI."""
    args = webservice_parse_args()

    if args.input_request:
        request_path = Path(args.input_request)
        if not request_path.exists():
            print(f"Request XML file not found: {request_path}")
            return
        payload = request_path.read_text(encoding="utf-8")
    else:
        webservice = WebserviceAPI()

        query = get_str_value(args.query, "expert query", default=None)
        page = get_int_value(args.page, "page", default=1)
        page_size = get_int_value(args.page_size, "page size", default=1)
        language = get_str_value(args.language, "search language", default="en")
        exclude_consleg = args.exclude_consleg
        latest_consleg = args.latest_consleg
        available_in = args.available_in

        payload = webservice.build_soap_payload(
            query=query,
            page=page,
            page_size=page_size,
            language=language,
            exclude_consleg=exclude_consleg,
            latest_consleg=latest_consleg,
            available_in=available_in
        )

        if args.save_request:
            Path(args.save_request).write_text(payload, encoding="utf-8")

    try:
        response_xml = WebserviceAPI.call_eurlex_webservice(payload)
        if args.references_only:
            references = WebserviceAPI.extract_references(response_xml)
            if references:
                for reference in references:
                    print(reference)
            else:
                print("No reference IDs found in response.")
        else:
            print("\n--- SOAP Response ---")
            print(response_xml)
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
