import argparse
from urllib.request import Request

from .etl.cellar_api import CellarAPI, CellarPS
from .etl.constants import MimeType, CollectionType, MAX_CS_SIZE


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


def main() -> None:
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
    main()
