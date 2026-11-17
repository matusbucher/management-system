from __future__ import annotations

from enum import Enum
from typing import Optional

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import Request, urlopen


_SOAP_ENDPOINT = "https://eur-lex.europa.eu/EURLexWebService"
_SOAP_ACTION = "https://eur-lex.europa.eu/EURLexWebService/doQuery"

_QUERY_PLACEHOLDER = "query"
_PAGE_PLACEHOLDER = "page"
_PAGE_SIZE_PLACEHOLDER = "page_size"
_LANGUAGE_PLACEHOLDER = "language"
_EXCLUDE_CONSLEG_PLACEHOLDER = "exclude_consleg"
_LATEST_CONSLEG_PLACEHOLDER = "latest_consleg"
_AVAILABLE_IN_PLACEHOLDER = "available_in"

_AVAILABLE_IN_TAG = "sear:showDocumentsAvailableIn"

_TEMPLATE_FILENAME = "templates/eurlex-search.xml"


class WebserviceAPI:
    """
    Wrapper class for EUR-Lex SOAP webservice.

    Default template path is "./templates/eurlex-search.xml".

    Args:
        template_path (Optional[Path]): The path to the SOAP template file. If None, the default template path is used.
    """
    
    def __init__(
        self,
        template_path: Optional[Path] = None
    ):
        if template_path is None:
            template_path = Path(__file__).parent.parent.parent / _TEMPLATE_FILENAME
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
        """
        Build the SOAP payload by replacing placeholders in the template with actual values.
        
        Args:
            query (str): The search query string.
            page (int): The page index for results.
            page_size (int): The number of results per page.
            language (str): The search language code.
            exclude_consleg (bool): Whether to exclude consolidated legislation.
            latest_consleg (bool): Whether to limit to the latest consolidated legislation.
            available_in (Optional[str]): The specific language to limit the search to (optional).

        Returns:
            str: The final SOAP payload as a string.
        """
        values = {
            _QUERY_PLACEHOLDER: query,
            _PAGE_PLACEHOLDER: str(page),
            _PAGE_SIZE_PLACEHOLDER: str(page_size),
            _LANGUAGE_PLACEHOLDER: language,
            _EXCLUDE_CONSLEG_PLACEHOLDER: "true" if exclude_consleg else "false",
            _LATEST_CONSLEG_PLACEHOLDER: "true" if latest_consleg else "false",
            _AVAILABLE_IN_PLACEHOLDER: available_in if available_in else "",
        }
        
        payload = self.template_text
        for key, value in values.items():
            payload = payload.replace(f"${{{key}}}", value)
        
        if not available_in:
            payload = re.sub(
                rf"\s*<{re.escape(_AVAILABLE_IN_TAG)}></{re.escape(_AVAILABLE_IN_TAG)}>\s*",
                "",
                payload
            )

        return payload

    @staticmethod
    def call_eurlex_webservice(
        payload: str
    ) -> str:
        """
        Call the EUR-Lex SOAP webservice with the given payload and return the response XML as a string.

        Args:
            payload (str): The SOAP payload to send in the request.

        Returns:
            str: The response XML as a string.
        """
        request = Request(
            url=_SOAP_ENDPOINT,
            data=payload.encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": f'application/soap+xml; charset=utf-8; action="{_SOAP_ACTION}"',
                "Accept": "application/soap+xml, text/xml, */*",
            },
        )

        with urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")

    @staticmethod
    def extract_references(
        response_xml: str
    ) -> list[str]:
        """
        Extract reference IDs from SOAP response XML.

        Args:
            response_xml (str): The SOAP response XML as a string.

        Returns:
            list[str]: A list of reference IDs extracted from the response.
        """
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
            query (str): Expert query string
            page (int): Page index for results (default: 1)
            page_size (int): Number of results per page (default: 1)
            language (str): Search language code (default: "en")
            exclude_consleg (bool): Exclude consolidated legislation (default: False)
            latest_consleg (bool): Limit to latest consolidated legislation (default: False)
            available_in (Optional[str]): Limit to specific languages (optional)
        
        Returns:
            list[str]: List of reference IDs (work UUIDs) from the search results.
        
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
            celex_numbers (str | list[str]): Single CELEX number or list of CELEX numbers
            page (int): Page index for results (default: 1)
            page_size (int): Number of results per page (default: 1)
            language (str): Search language code (default: "en")
        
        Returns:
            list[str]: List of reference IDs (work UUIDs) matching the CELEX numbers.
        
        Raises:
            HTTPError: If the webservice returns an HTTP error.
            URLError: If there's a connection error.
            Exception: For other unexpected errors.
        """
        if isinstance(celex_numbers, str):
            query = f'DN="{celex_numbers}"'
        else:
            subqueries = [f'DN="{celex}"' for celex in celex_numbers]
            query = " OR ".join(subqueries)
        
        return self.search(
            query=query,
            page=page,
            page_size=page_size,
            language=language
        )