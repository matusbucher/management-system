from __future__ import annotations

import argparse
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


def cellar_parse_args() -> argparse.Namespace:
    """Parse command-line arguments for Cellar API.
    
    Returns:
        Parsed command-line arguments as argparse.Namespace.
    """
    parser = argparse.ArgumentParser(
        description="Cellar API request builder - Create HTTP requests for Cellar resources."
    )
    
    subparsers = parser.add_subparsers(
        dest="command",
        help="Command to execute"
    )
    
    # Subcommand: build-ps-id
    ps_id_parser = subparsers.add_parser(
        "build-ps-id",
        help="Build a production system ID"
    )
    ps_id_parser.add_argument(
        "-p", "--ps",
        choices=["cellar", "others"],
        required=True,
        help="Production system type"
    )
    ps_id_parser.add_argument(
        "-w", "--work-id",
        required=True,
        help="Work ID (UUID for Cellar, alphanumeric for Others)"
    )
    ps_id_parser.add_argument(
        "-e", "--expr-id",
        help="Expression ID (4-digit for Cellar, ISO 639-3 for Others)"
    )
    ps_id_parser.add_argument(
        "-m", "--man-id",
        help="Manifestation ID (2-digit for Cellar, format name for Others)"
    )
    ps_id_parser.add_argument(
        "-c", "--cs-id",
        help="Content stream ID"
    )
    
    # Subcommand: build-uri
    uri_parser = subparsers.add_parser(
        "build-uri",
        help="Build a resource URI"
    )
    uri_parser.add_argument(
        "-p", "--ps",
        choices=["cellar", "others"],
        required=True,
        help="Production system type"
    )
    uri_parser.add_argument(
        "-i", "--ps-id",
        required=True,
        help="Production system ID"
    )
    
    # Subcommand: build-request
    req_parser = subparsers.add_parser(
        "build-request",
        help="Build an HTTP request"
    )
    req_parser.add_argument(
        "-p", "--ps",
        choices=["cellar", "others"],
        required=True,
        help="Production system type"
    )
    req_parser.add_argument(
        "-i", "--ps-id",
        required=True,
        help="Production system ID"
    )
    req_parser.add_argument(
        "--type",
        choices=[
            "tree-notice",
            "branch-notice",
            "object-notice",
            "identifiers-notice",
            "metadata",
            "metadata-tree",
            "content-stream",
            "content-stream-collection"
        ],
        required=True,
        help="Request type"
    )
    req_parser.add_argument(
        "--dec-lang",
        help="Decoding language (ISO 639-3 code)"
    )
    req_parser.add_argument(
        "--acc-lang",
        help="Accept language (ISO 639-3 code)"
    )
    req_parser.add_argument(
        "--normalized",
        action="store_true",
        help="Request normalized metadata"
    )
    req_parser.add_argument(
        "--non-inferred",
        action="store_true",
        help="Exclude inferred triples"
    )
    req_parser.add_argument(
        "--alternates",
        action="store_true",
        help="Include alternate representations"
    )
    req_parser.add_argument(
        "--mime-type",
        choices=["xml", "html", "pdf", "rdf_xml"],
        default="xml",
        help="MIME type"
    )
    req_parser.add_argument(
        "--collection-type",
        choices=["list", "zip"],
        default="list",
        help="Collection type"
    )
    req_parser.add_argument(
        "--size",
        type=int,
        help="Maximum content stream size"
    )
    
    return parser.parse_args()


def cellar_cli() -> None:
    """Main entry point for the Cellar API CLI."""
    args = cellar_parse_args()
    
    if not args.command:
        return
    
    try:
        ps_enum = getattr(CellarPS, args.ps.upper())
        
        if args.command == "build-ps-id":
            if args.ps == "cellar":
                result = CellarAPI.cellar_ps_id(args.work_id, args.expr_id, args.man_id, args.cs_id)
            else:
                result = CellarAPI.others_ps_id(args.work_id, args.expr_id, args.man_id, args.cs_id)
            print(result)
        
        elif args.command == "build-uri":
            result = CellarAPI.construct_resource_uri(ps_enum, args.ps_id)
            print(result)
        
        elif args.command == "build-request":
            req = Request("")

            if args.type == "tree-notice":
                req = CellarAPI.tree_notice_request(ps_enum, args.ps_id, args.dec_lang)
            elif args.type == "branch-notice":
                req = CellarAPI.branch_notice_request(ps_enum, args.ps_id, args.dec_lang, args.acc_lang or "eng")
            elif args.type == "object-notice":
                req = CellarAPI.object_notice_request(ps_enum, args.ps_id, args.dec_lang, args.acc_lang, args.alternates)
            elif args.type == "identifiers-notice":
                req = CellarAPI.indentifiers_notice_request(ps_enum, args.ps_id)
            elif args.type == "metadata":
                req = CellarAPI.metadata_request(ps_enum, args.ps_id, args.dec_lang, args.normalized, args.non_inferred, args.alternates)
            elif args.type == "metadata-tree":
                req = CellarAPI.metadata_tree_request(ps_enum, args.ps_id, args.dec_lang, args.normalized, args.non_inferred)
            elif args.type == "content-stream":
                mime_type = getattr(MimeType, args.mime_type.upper())
                req = CellarAPI.content_stream_request(ps_enum, args.ps_id, args.dec_lang, mime_type, args.acc_lang or "eng", args.size or MAX_CS_SIZE)
            elif args.type == "content-stream-collection":
                mime_type = getattr(MimeType, args.mime_type.upper())
                collection_type = getattr(CollectionType, args.collection_type.upper())
                req = CellarAPI.content_stream_collection_request(ps_enum, args.ps_id, args.dec_lang, collection_type, mime_type, args.acc_lang or "eng")
            
            print(f"Method: {req.get_method()}")
            print(f"URL: {req.full_url}")
            print("Headers:")
            for key, value in req.headers.items():
                print(f"  {key}: {value}")
    
    except ValueError as e:
        print(f"Error: {str(e)}")
        exit(1)
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        exit(1)


if __name__ == "__main__":
    cellar_cli()
