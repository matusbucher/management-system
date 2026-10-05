from __future__ import annotations

import argparse
import sys
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from typing import Optional

from .constants import *
from .utils import *


class WebserviceAPI:
    """
    Wrapper class for EUR-Lex SOAP webservice.
    """
    
    def __init__(self):
        """Initialize the webservice caller."""
        template_path = Path(__file__).parent.parent.parent / TEMPLATE_FILENAME
        if not template_path.exists():
            raise FileNotFoundError(f"SOAP template file not found: {template_path}")
        self.template_text = template_path.read_text(encoding="utf-8")

    def build_soap_payload(
        self,
        query: str,
        page: int = 1,
        page_size: int = 1,
        language: str = "en",
        exclude_consleg: bool = False,
        latest_consleg: bool = False,
        available_in: Optional[str] = None,
    ) -> str:
        """Build the SOAP payload by replacing placeholders in the template with actual values.
        
        Args:
            query: The search query string.
            page: The page index for results.
            page_size: The number of results per page.
            language: The search language code.
            exclude_consleg: Whether to exclude consolidated legislation.
            latest_consleg: Whether to limit to the latest consolidated legislation.
            available_in: The specific language to limit the search to (optional).

        Returns:
            The final SOAP payload as a string.
        """
        values = {
            "query": query,
            "page": str(page),
            "page_size": str(page_size),
            "language": language,
            "exclude_consleg": "true" if exclude_consleg else "false",
            "latest_consleg": "true" if latest_consleg else "false",
            "available_in": available_in if available_in else "",
        }
        
        payload = self.template_text
        for key, value in values.items():
            payload = payload.replace(f"${{{key}}}", value)
        
        if not available_in:
            payload = re.sub(
                rf"\s*<{re.escape(AVAILABLE_IN_TAG)}></{re.escape(AVAILABLE_IN_TAG)}>\s*",
                "",
                payload
            )

        return payload

    @classmethod
    def call_eurlex_webservice(cls, payload: str) -> str:
        """Call the EUR-Lex SOAP webservice with the given payload and return the response XML as a string."""
        request = Request(
            url=SOAP_ENDPOINT,
            data=payload.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION}"',
                "Accept": "application/soap+xml, text/xml, */*",
            },
        )

        with urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")

    @classmethod
    def extract_references(cls, response_xml: str) -> list[str]:
        """Extract reference IDs from SOAP response XML."""
        root = ET.fromstring(response_xml)
        references: list[str] = []
        for element in root.iter():
            if element.tag.endswith("reference") and element.text:
                references.append(element.text.strip())
        return references
    
    def search(
        self,
        query: str,
        page: int = 1,
        page_size: int = 1,
        language: str = "en",
        exclude_consleg: bool = False,
        latest_consleg: bool = False,
        available_in: Optional[str] = None,
    ) -> list[str]:
        """
        Search for documents using the EUR-Lex SOAP webservice.
        
        Args:
            query: Expert query string
            page: Page index for results (default: 1)
            page_size: Number of results per page (default: 1)
            language: Search language code (default: "en")
            exclude_consleg: Exclude consolidated legislation (default: False)
            latest_consleg: Limit to latest consolidated legislation (default: False)
            available_in: Limit to specific languages (optional)
        
        Returns:
            List of reference IDs (work UUIDs) from the search results.
        
        Raises:
            HTTPError: If the webservice returns an HTTP error.
            URLError: If there's a connection error.
            Exception: For other unexpected errors.
        """
        payload = self.build_soap_payload(
            query=query,
            page=page,
            page_size=page_size,
            language=language,
            exclude_consleg=exclude_consleg,
            latest_consleg=latest_consleg,
            available_in=available_in
        )
        
        response_xml = self.call_eurlex_webservice(payload)
        return self.extract_references(response_xml)
    
    def search_by_celex(
        self,
        celex_numbers: str | list[str],
        page: int = 1,
        page_size: int = 1,
        language: str = "en",
    ) -> list[str]:
        """
        Search for documents by CELEX number(s).
        
        Args:
            celex_numbers: Single CELEX number or list of CELEX numbers
            page: Page index for results (default: 1)
            page_size: Number of results per page (default: 1)
            language: Search language code (default: "en")
        
        Returns:
            List of reference IDs (work UUIDs) matching the CELEX numbers.
        
        Raises:
            HTTPError: If the webservice returns an HTTP error.
            URLError: If there's a connection error.
            Exception: For other unexpected errors.
        """
        if isinstance(celex_numbers, str):
            query = f'DN = "{celex_numbers}"'
        else:
            quoted = [f'"{celex}"' for celex in celex_numbers]
            query = f'DN IN ({", ".join(quoted)})'
        
        return self.search(
            query=query,
            page=page,
            page_size=page_size,
            language=language
        )


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


def webservice_cli() -> None:
    """Main entry point for the Webservice API CLI."""
    args = webservice_parse_args()

    if args.input_request:
        request_path = Path(args.input_request)
        if not request_path.exists():
            print(f"Request XML file not found: {request_path}")
            return
        payload = request_path.read_text(encoding="utf-8")
    else:
        caller = WebserviceAPI()

        query = get_str_value(args.query, "expert query", default=None)
        page = get_int_value(args.page, "page", default=1)
        page_size = get_int_value(args.page_size, "page size", default=1)
        language = get_str_value(args.language, "search language", default="en")
        exclude_consleg = args.exclude_consleg
        latest_consleg = args.latest_consleg
        available_in = args.available_in

        payload = caller.build_soap_payload(
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
    webservice_cli()