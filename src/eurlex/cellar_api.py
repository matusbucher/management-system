from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request

from .constants import *
from .utils import *


class CellarAPI:
    """
    Wrapper class for Cellar API operations.
    
    Provides methods for constructing production system IDs, URIs, and HTTP requests
    for accessing Cellar resources through various endpoints.
    """
    
    @classmethod
    def cellar_ps_id(
        cls,
        work_id: str,
        expr_id: Optional[str] = None,
        man_id: Optional[str] = None,
        cs_id: Optional[str] = None
    ) -> str:
        """
        Build a Cellar production system ID for a resource.
        
        Args:
            work_id: Work ID (must be a valid UUID)
            expr_id: Expression ID (optional, 4-character numeric)
            man_id: Manifestation ID (optional, 2-character numeric)
            cs_id: Content stream ID (optional, pattern DOC_x where x is numeric)
        
        Returns:
            The complete Cellar production system ID string.
        
        Raises:
            ValueError: If any ID parameter has invalid format or invalid hierarchy.
        """
        if not UUID_PATTERN.match(work_id):
            raise ValueError("Work ID must be a valid UUID.")
        if expr_id and not CELLAR_EXPR_ID_PATTERN.match(expr_id):
            raise ValueError("Expression ID must be a 4-character numeric value.")
        if man_id and not CELLAR_MAN_ID_PATTERN.match(man_id):
            raise ValueError("Manifestation ID must be a 2-character numeric value.")
        if cs_id and not CELLAR_CS_ID_PATTERN.match(cs_id):
            raise ValueError("Content stream ID must follow the pattern DOC_x where x is numeric.")

        if man_id and not expr_id:
            raise ValueError("Manifestation ID requires an Expression ID.")
        if cs_id and not man_id:
            raise ValueError("Content stream ID requires a Manifestation ID.")

        ps_id = work_id
        if expr_id:
            ps_id += f".{expr_id}"
        if man_id:
            ps_id += f".{man_id}"
        if cs_id:
            ps_id += f"/{cs_id}"

        return ps_id

    @classmethod
    def others_ps_id(
        cls,
        work_id: str,
        expr_id: Optional[str] = None,
        man_id: Optional[str] = None,
        cs_id: Optional[str] = None
    ) -> str:
        """
        Build a production system ID for non-Cellar resources.
        
        Args:
            work_id: Work ID (must be alphanumeric)
            expr_id: Expression ID (optional, valid 3-character ISO 639-3 language code)
            man_id: Manifestation ID (optional, valid file format)
            cs_id: Content stream ID (optional)
        
        Returns:
            The complete production system ID string.
        
        Raises:
            ValueError: If any ID parameter has invalid format or invalid hierarchy.
        """
        if not work_id.isalnum():
            raise ValueError("Work ID must be an alphanumeric value.")
        if expr_id and expr_id not in ISO_639_3_CODES:
            raise ValueError("Expression ID must be a valid 3-character ISO 639-3 language code.")
        if man_id and man_id not in MANIFESTATION_FORMATS:
            raise ValueError("Manifestation ID must be a valid file format.")
         
        if man_id and not expr_id:
            raise ValueError("Manifestation ID requires an Expression ID.")
        if cs_id and not man_id:
            raise ValueError("Content stream ID requires a Manifestation ID.")

        ps_id = work_id
        if expr_id:
            ps_id += f".{expr_id}"
        if man_id:
            ps_id += f".{man_id}"
        if cs_id:
            ps_id += f".{cs_id}"

        return ps_id

    @classmethod
    def construct_resource_uri(cls, ps: CellarPS, ps_id: str) -> str:
        """
        Construct the full resource URI for a Cellar resource.
        
        Args:
            ps: The CellarPS production system type (CELLAR or OTHERS)
            ps_id: The production system ID
        
        Returns:
            The complete resource URI string.
        """
        return f"{RESOURCE_BASE_URL}/{ps.value}/{ps_id}"

    @classmethod
    def tree_notice_request(
        cls,
        ps: CellarPS,
        ps_id: str,
        dec_lang: Optional[str] = None
    ) -> Request:
        """
        Create a tree notice HTTP request for a resource.

        The returned notice will contain the work metadata, the metadata of all the expressions
        associated to the work, and the metadata of all the manifestations associated to the
        expressions.
        
        Args:
            ps: The CellarPS production system type
            ps_id: The production system ID
            dec_lang: Decoding language (optional, valid 3-character ISO 639-3 code)
        
        Returns:
            An HTTP Request object configured for tree notice retrieval.
        
        Raises:
            ValueError: If dec_lang is not a valid ISO 639-3 code.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(ps, ps_id)
        headers = {
            "Accept": "application/xml;notice=tree"
        }

        if dec_lang:
            query = urlencode({"language": dec_lang.lower()})
            url += f"?{query}"

        return Request(url=url, headers=headers, method="GET")

    @classmethod
    def branch_notice_request(
        cls,
        ps: CellarPS,
        ps_id: str,
        dec_lang: Optional[str] = None,
        acc_lang: str = "eng"
    ) -> Request:
        """
        Create a branch notice HTTP request for a resource.

        The returned notice will contain the work metadata, the metadata of the expression
        in the given accept language, and the metadata of all manifestations associated
        to the expression.
        
        Args:
            ps: The CellarPS production system type
            ps_id: The production system ID
            dec_lang: Decoding language (optional, valid 3-character ISO 639-3 code)
            acc_lang: Accept language (default: "eng", valid 3-character ISO 639-3 code)
        
        Returns:
            An HTTP Request object configured for branch notice retrieval.
        
        Raises:
            ValueError: If any language code is not valid ISO 639-3.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        if acc_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Accept language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(ps, ps_id)
        headers = {
            "Accept": "application/xml;notice=branch",
            "Accept-Language": acc_lang.lower()
        }

        if dec_lang:
            query = urlencode({"language": dec_lang.lower()})
            url += f"?{query}"

        return Request(url=url, headers=headers, method="GET")

    @classmethod
    def object_notice_request(
        cls,
        ps: CellarPS,
        ps_id: str,
        dec_lang: Optional[str] = None,
        acc_lang: Optional[str] = None,
        alternates: bool = False
    ) -> Request:
        """
        Create an object notice HTTP request for a resource.

        Only the metadata of the one level (work/expression/manifestation) are returned in the notice.
        
        Args:
            ps: The CellarPS production system type
            ps_id: The production system ID
            dec_lang: Decoding language (optional, valid 3-character ISO 639-3 code)
            acc_lang: Accept language (optional, valid 3-character ISO 639-3 code)
            alternates: Include alternate representations (default: False)
        
        Returns:
            An HTTP Request object configured for object notice retrieval.
        
        Raises:
            ValueError: If any language code is not valid ISO 639-3.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        if acc_lang and acc_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Accept language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(ps, ps_id)
        headers = {
            "Accept": "application/xml;notice=object",
        }

        if dec_lang:
            query = urlencode({"language": dec_lang.lower()})
            url += f"?{query}"

        if acc_lang:
            headers["Accept-Language"] = acc_lang.lower()
        
        if alternates:
            headers["Negotiate"] = "vlist"

        return Request(url=url, headers=headers, method="GET")

    @classmethod
    def indentifiers_notice_request(cls, ps: CellarPS, ps_id: str) -> Request:
        """
        Create an identifiers notice HTTP request for a resource.

        This service allows the user to retrieve the synonyms of a given resource URI.
        
        Args:
            ps: The CellarPS production system type
            ps_id: The production system ID
        
        Returns:
            An HTTP Request object configured for identifiers notice retrieval.
        """
        url = cls.construct_resource_uri(ps, ps_id)
        headers = {
            "Accept": "application/xml;notice=identifiers"
        }

        return Request(url=url, headers=headers, method="GET")

    @classmethod
    def metadata_request(
        cls,
        ps: CellarPS,
        ps_id: str,
        dec_lang: Optional[str] = None,
        normalized: bool = False,
        non_inferred: bool = False,
        alternates: bool = False
    ) -> Request:
        """
        Create a metadata HTTP request for a resource.

        This service allows the user to search for the RDF content of the given object in
        RDF/XML format. The object to search for can be a work, an expression, a manifestation,
        a dossier, an event, a top level event or an agent.

        Args:
            ps: The CellarPS production system type
            ps_id: The production system ID
            dec_lang: Decoding language (optional, valid 3-character ISO 639-3 code)
            normalized: Request normalized metadata (default: False)
            non_inferred: Exclude inferred triples (default: False)
            alternates: Include alternate representations (default: False)
        
        Returns:
            An HTTP Request object configured for metadata retrieval in RDF/XML format.
        
        Raises:
            ValueError: If dec_lang is not a valid ISO 639-3 code.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(ps, ps_id)
        headers = {
            "Accept": "application/rdf+xml"
        }

        if dec_lang:
            query = urlencode({"language": dec_lang.lower()})
            url += f"?{query}"

        if normalized and non_inferred:
            headers["Accept"] += ";notice=non-inferred-normalized"
        elif normalized:
            headers["Accept"] += ";notice=normalized"
        elif non_inferred:
            headers["Accept"] += ";notice=non-inferred"

        if alternates:
            headers["Negotiate"] = "vlist"

        return Request(url=url, headers=headers, method="GET")

    @classmethod
    def metadata_tree_request(
        cls,
        ps: CellarPS,
        ps_id: str,
        dec_lang: Optional[str] = None,
        normalized: bool = False,
        non_inferred: bool = False
    ) -> Request:
        """
        Create a metadata tree HTTP request for a resource.

        This service allows the user to search for the RDF tree whose root is the given object.
        The object to search for can be a work, a dossier, a top level event or an agent.

        Args:
            ps: The CellarPS production system type
            ps_id: The production system ID
            dec_lang: Decoding language (optional, valid 3-character ISO 639-3 code)
            normalized: Request normalized metadata (default: False)
            non_inferred: Exclude inferred triples (default: False)
        
        Returns:
            An HTTP Request object configured for metadata tree retrieval in RDF/XML format.
        
        Raises:
            ValueError: If dec_lang is not a valid ISO 639-3 code.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(ps, ps_id)
        headers = {
            "Accept": "application/rdf+xml"
        }

        if dec_lang:
            query = urlencode({"language": dec_lang.lower()})
            url += f"?{query}"

        if normalized and non_inferred:
            headers["Accept"] += ";notice=non-inferred-tree-normalized"
        elif normalized:
            headers["Accept"] += ";notice=tree-normalized"
        elif non_inferred:
            headers["Accept"] += ";notice=non-inferred-tree"
        else:
            headers["Accept"] += ";notice=tree"

        return Request(url=url, headers=headers, method="GET")

    @classmethod
    def content_stream_request(
        cls,
        ps: CellarPS,
        ps_id: str,
        dec_lang: Optional[str] = None,
        mime_type: MimeType = MimeType.XML,
        acc_lang: str = "eng",
        size: int = MAX_CS_SIZE
    ) -> Request:
        """
        Create a content stream HTTP request for a resource.

        This service allows the user to retrieve the content stream of the manifestation belonging
        to the given work and to the expression in the given accept language, and which contains
        at least one content stream of the given accept format.
        
        Args:
            ps: The CellarPS production system type
            ps_id: The production system ID
            dec_lang: Decoding language (optional, valid 3-character ISO 639-3 code)
            mime_type: MIME type for content (default: MimeType.XML)
            acc_lang: Accept language (default: "eng", valid 3-character ISO 639-3 code)
            size: Maximum content stream size in bytes (default: MAX_CS_SIZE)
        
        Returns:
            An HTTP Request object configured for content stream retrieval.
        
        Raises:
            ValueError: If dec_lang is not a valid ISO 639-3 code.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(ps, ps_id)
        headers = {
            "Accept": mime_type.value,
            "Accept-Language": acc_lang.lower(),
            "Accept-Max-Cs-Size": str(size)
        }

        if dec_lang:
            query = urlencode({"language": dec_lang.lower()})
            url += f"?{query}"

        return Request(url=url, headers=headers, method="GET")

    @classmethod
    def content_stream_collection_request(
        cls,
        ps: CellarPS,
        ps_id: str,
        dec_lang: Optional[str] = None,
        collection_type: CollectionType = CollectionType.LIST,
        mime_type: MimeType = MimeType.XML,
        acc_lang: str = "eng"
    ) -> Request:
        """
        Create a content stream collection HTTP request for a resource.

        This service allows the user to retrieve a collection (in zip or list format) of the
        content streams of the manifestation belonging to the given work and to the expression
        in the given accept language, and which contains at least one content stream of the
        given accept format.
        
        Args:
            ps: The CellarPS production system type
            ps_id: The production system ID
            dec_lang: Decoding language (optional, valid 3-character ISO 639-3 code)
            collection_type: Collection format type (default: CollectionType.LIST)
            mime_type: MIME type for content (default: MimeType.XML)
            acc_lang: Accept language (default: "eng", valid 3-character ISO 639-3 code)
        
        Returns:
            An HTTP Request object configured for content stream collection retrieval.
        
        Raises:
            ValueError: If dec_lang is not a valid ISO 639-3 code.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(ps, ps_id)
        headers = {
            "Accept": f"application/{collection_type.value};mtype={mime_type.value}",
            "Accept-Language": acc_lang.lower()
        }

        if dec_lang:
            query = urlencode({"language": dec_lang.lower()})
            url += f"?{query}"

        return Request(url=url, headers=headers, method="GET")
