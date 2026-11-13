from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen

from typing import Optional

from .constants import *


class WebserviceAPI:
    """
    Wrapper class for EUR-Lex SOAP webservice.
    """
    
    def __init__(self):
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
            SearchPlaceholder.QUERY.value: query,
            SearchPlaceholder.PAGE.value: str(page),
            SearchPlaceholder.PAGE_SIZE.value: str(page_size),
            SearchPlaceholder.LANGUAGE.value: language,
            SearchPlaceholder.EXCLUDE_CONSLEG.value: "true" if exclude_consleg else "false",
            SearchPlaceholder.LATEST_CONSLEG.value: "true" if latest_consleg else "false",
            SearchPlaceholder.AVAILABLE_IN.value: available_in if available_in else "",
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
