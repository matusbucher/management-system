from __future__ import annotations

from typing import Optional
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request

from .constants import *


@dataclass
class CellarResourceId:
    """
    Represents a CELLAR resource's unique identifier.

    The structure of the identifier depends on the production system (CELLAR or other).

    Args:
        ps (CellarPS): The production system name
        work_id (str): Work ID
        expr_id (Optional[str]): Expression ID (optional)
        man_id (Optional[str]): Manifestation ID (optional)
        cs_id (Optional[str]): Content stream ID (optional)
    """
    ps: CellarPS
    work_id: str
    expr_id: Optional[str] = None
    man_id: Optional[str] = None
    cs_id: Optional[str] = None

    def __post_init__(self):
        if self.man_id and not self.expr_id:
            raise ValueError("Manifestation ID requires an Expression ID.")
        if self.cs_id and not self.man_id:
            raise ValueError("Content stream ID requires a Manifestation ID.")

        if self.ps == CellarPS.CELLAR:
            self._check_cellar_uri(self.work_id, self.expr_id, self.man_id, self.cs_id)
        else:
            self._check_other_uri(self.work_id, self.expr_id, self.man_id, self.cs_id)

    def __str__(self) -> str:
        uri = f"{self.ps.value}/{self.work_id}"
        if self.expr_id:
            uri += f".{self.expr_id}"
        if self.man_id:
            uri += f".{self.man_id}"
        if self.cs_id:
            if self.ps == CellarPS.CELLAR:
                uri += f"/{self.cs_id}"
            else:
                uri += f".{self.cs_id}"
        return uri

    @classmethod
    def _check_cellar_uri(
        cls,
        work_id: str,
        expr_id: Optional[str] = None,
        man_id: Optional[str] = None,
        cs_id: Optional[str] = None
    ) -> None:
        """
        Validate a CELLAR production system resource identifier according to CELLAR-specific rules.

        Args:
            work_id (str): Work ID (must be a valid UUID)
            expr_id (Optional[str]): Expression ID (optional, 4-character numeric)
            man_id (Optional[str]): Manifestation ID (optional, 2-character numeric)
            cs_id (Optional[str]): Content stream ID (optional, pattern DOC_x where x is numeric)

        Raises:
            ValueError: If any ID parameter has invalid format.
        """
        if not UUID_PATTERN.match(work_id):
            raise ValueError("Work ID must be a valid UUID.")
        if expr_id and not CELLAR_EXPR_ID_PATTERN.match(expr_id):
            raise ValueError("Expression ID must be a 4-character numeric value.")
        if man_id and not CELLAR_MAN_ID_PATTERN.match(man_id):
            raise ValueError("Manifestation ID must be a 2-character numeric value.")
        if cs_id and not CELLAR_CS_ID_PATTERN.match(cs_id):
            raise ValueError("Content stream ID must follow the pattern DOC_x where x is numeric.")

    @classmethod
    def _check_other_uri(
        cls,
        work_id: str,
        expr_id: Optional[str] = None,
        man_id: Optional[str] = None,
        cs_id: Optional[str] = None
    ) -> None:
        """
        Validate a non-CELLAR production system resource identifier according to general rules.

        Args:
            work_id (str): Work ID (alphanumeric)
            expr_id (Optional[str]): Expression ID (optional, 3-character ISO 639-3 language code)
            man_id (Optional[str]): Manifestation ID (optional, valid file format)
            cs_id (Optional[str]): Content stream ID (optional, alphanumeric)

        Raises:
            ValueError: If any ID parameter has invalid format.
        """
        if not work_id.isalnum():
            raise ValueError("Work ID must be an alphanumeric value.")
        if expr_id and expr_id not in ISO_639_3_CODES:
            raise ValueError("Expression ID must be a valid 3-character ISO 639-3 language code.")
        if man_id and man_id not in MANIFESTATION_FORMATS:
            raise ValueError("Manifestation ID must be a valid file format.")
        if cs_id and not cs_id.isalnum():
            raise ValueError("Content stream ID must be an alphanumeric value.")

    @classmethod
    def from_string(
        cls,
        uri: str
    ) -> CellarResourceId:
        """
        Create a CellarResourceId object from a resource URI.

        Args:
            uri (str): The resource URI string

        Returns:
            CellarResourceId: The corresponding CELLAR resource identifier object

        Raises:
            ValueError: If the URI format is invalid.
        """
        try:
            ps_name, resource_id = uri.rsplit("/", 1)
            ps = CellarPS.from_string(ps_name)
            parts = resource_id.split("/")
            work_id = parts[0]
            expr_id = parts[1] if len(parts) > 1 else None
            man_id = parts[2] if len(parts) > 2 else None
            cs_id = parts[3] if len(parts) > 3 else None
            return CellarResourceId(ps, work_id, expr_id, man_id, cs_id)

        except Exception as e:
            raise ValueError(f"Invalid URI format: {uri}") from e



class CellarAPI:
    """
    Wrapper class for CELLAR API services.
    """

    @classmethod
    def construct_resource_uri(
        cls,
        resource_id: CellarResourceId
    ) -> str:
        """
        Construct the full resource URI for a CELLAR resource.
        
        Args:
            resource_id (CellarResourceId): The CELLAR resource identifier object
        
        Returns:
            The complete resource URI string.
        """
        return f"{RESOURCE_BASE_URL}/{resource_id}"

    @classmethod
    def tree_notice_request(
        cls,
        resource_id: CellarResourceId,
        dec_lang: Optional[str] = None
    ) -> Request:
        """
        Create a tree notice HTTP request for a resource.

        The returned notice will contain the work metadata, the metadata of all the expressions
        associated to the work, and the metadata of all the manifestations associated to the
        expressions.
        
        Args:
            resource_id (CellarResourceId): The CELLAR resource identifier object
            dec_lang (Optional[str]): Decoding language (optional, valid 3-character ISO 639-3 code)
        
        Returns:
            An HTTP Request object configured for tree notice retrieval.
        
        Raises:
            ValueError: If dec_lang is not a valid ISO 639-3 code.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(resource_id)
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
        resource_id: CellarResourceId,
        dec_lang: Optional[str] = None,
        acc_lang: str = "eng"
    ) -> Request:
        """
        Create a branch notice HTTP request for a resource.

        The returned notice will contain the work metadata, the metadata of the expression
        in the given accept language, and the metadata of all manifestations associated
        to the expression.
        
        Args:
            resource_id (CellarResourceId): The CELLAR resource identifier object
            dec_lang (Optional[str]): Decoding language (optional, valid 3-character ISO 639-3 code)
            acc_lang (str): Accept language (default: "eng", valid 3-character ISO 639-3 code)
        
        Returns:
            An HTTP Request object configured for branch notice retrieval.
        
        Raises:
            ValueError: If any language code is not valid ISO 639-3.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        if acc_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Accept language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(resource_id)
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
        resource_id: CellarResourceId,
        dec_lang: Optional[str] = None,
        acc_lang: Optional[str] = None,
        alternates: bool = False
    ) -> Request:
        """
        Create an object notice HTTP request for a resource.

        Only the metadata of the one level (work/expression/manifestation) are returned in the notice.
        
        Args:
            resource_id (CellarResourceId): The CELLAR resource identifier object
            dec_lang (Optional[str]): Decoding language (optional, valid 3-character ISO 639-3 code)
            acc_lang (Optional[str]): Accept language (optional, valid 3-character ISO 639-3 code)
            alternates (bool): Include alternate representations (default: False)
        
        Returns:
            An HTTP Request object configured for object notice retrieval.
        
        Raises:
            ValueError: If any language code is not valid ISO 639-3.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        if acc_lang and acc_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Accept language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(resource_id)
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
    def indentifiers_notice_request(
        cls,
        resource_id: CellarResourceId
    ) -> Request:
        """
        Create an identifiers notice HTTP request for a resource.

        This service allows the user to retrieve the synonyms of a given resource URI.
        
        Args:
            resource_id (CellarResourceId): The CELLAR resource identifier object
        
        Returns:
            An HTTP Request object configured for identifiers notice retrieval.
        """
        url = cls.construct_resource_uri(resource_id)
        headers = {
            "Accept": "application/xml;notice=identifiers"
        }

        return Request(url=url, headers=headers, method="GET")

    @classmethod
    def metadata_request(
        cls,
        resource_id: CellarResourceId,
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
            resource_id (CellarResourceId): The CELLAR resource identifier object
            dec_lang (Optional[str]): Decoding language (optional, valid 3-character ISO 639-3 code)
            normalized (bool): Request normalized metadata (default: False)
            non_inferred (bool): Exclude inferred triples (default: False)
            alternates (bool): Include alternate representations (default: False)
        
        Returns:
            An HTTP Request object configured for metadata retrieval in RDF/XML format.
        
        Raises:
            ValueError: If dec_lang is not a valid ISO 639-3 code.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(resource_id)
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
        resource_id: CellarResourceId,
        dec_lang: Optional[str] = None,
        normalized: bool = False,
        non_inferred: bool = False
    ) -> Request:
        """
        Create a metadata tree HTTP request for a resource.

        This service allows the user to search for the RDF tree whose root is the given object.
        The object to search for can be a work, a dossier, a top level event or an agent.

        Args:
            resource_id (CellarResourceId): The CELLAR resource identifier object
            dec_lang (Optional[str]): Decoding language (optional, valid 3-character ISO 639-3 code)
            normalized (bool): Request normalized metadata (default: False)
            non_inferred (bool): Exclude inferred triples (default: False)
        
        Returns:
            Request: An HTTP Request object configured for metadata tree retrieval in RDF/XML format.
        
        Raises:
            ValueError: If dec_lang is not a valid ISO 639-3 code.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(resource_id)
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
        resource_id: CellarResourceId,
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
            resource_id (CellarResourceId): The CELLAR resource identifier object
            dec_lang (Optional[str]): Decoding language (optional, valid 3-character ISO 639-3 code)
            mime_type (MimeType): MIME type for content (default: MimeType.XML)
            acc_lang (str): Accept language (default: "eng", valid 3-character ISO 639-3 code, must be in ISO_639_3_CODES)
            size (int): Maximum content stream size in bytes (default: MAX_CS_SIZE)
        
        Returns:
            Request: An HTTP Request object configured for content stream retrieval.
        
        Raises:
            ValueError: If dec_lang or acc_lang is not a valid ISO 639-3 code.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        if acc_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Accept language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(resource_id)
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
        resource_id: CellarResourceId,
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
            resource_id (CellarResourceId): The CELLAR resource identifier object
            dec_lang (Optional[str]): Decoding language (optional, valid 3-character ISO 639-3 code)
            collection_type (CollectionType): Collection format type (default: CollectionType.LIST)
            mime_type (MimeType): MIME type for content (default: MimeType.XML)
            acc_lang (str): Accept language (default: "eng", valid 3-character ISO 639-3 code, must be in ISO_639_3_CODES)
        
        Returns:
            Request: An HTTP Request object configured for content stream collection retrieval.
        
        Raises:
            ValueError: If dec_lang or acc_lang is not a valid ISO 639-3 code.
        """
        if dec_lang and dec_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Decoding language must be a valid 3-character ISO 639-3 code.")
        if acc_lang.upper() not in ISO_639_3_CODES:
            raise ValueError("Accept language must be a valid 3-character ISO 639-3 code.")
        
        url = cls.construct_resource_uri(resource_id)
        headers = {
            "Accept": f"application/{collection_type.value};mtype={mime_type.value}",
            "Accept-Language": acc_lang.lower()
        }

        if dec_lang:
            query = urlencode({"language": dec_lang.lower()})
            url += f"?{query}"

        return Request(url=url, headers=headers, method="GET")
