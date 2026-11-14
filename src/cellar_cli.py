import argparse
from urllib.request import Request

from eurlex.cellar_api import CellarResourceId, CellarAPI
from eurlex.constants import CellarPS, MimeType, CollectionType, MAX_CS_SIZE


def cellar_parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for Cellar API.
    
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
        "build-rid",
        help="Build a resource ID"
    )
    ps_id_parser.add_argument(
        "-p", "--ps",
        choices=[ps.value for ps in CellarPS],
        required=True,
        help="Production system type"
    )
    ps_id_parser.add_argument(
        "-w", "--work-id",
        required=True,
        help="Work ID (UUID for cellar PS; alphanumeric for others)"
    )
    ps_id_parser.add_argument(
        "-e", "--expr-id",
        help="Expression ID (4-character numeric for cellar PS; ISO 639-3 for others)"
    )
    ps_id_parser.add_argument(
        "-m", "--man-id",
        help="Manifestation ID (2-character numeric for cellar PS; valid file format for others)"
    )
    ps_id_parser.add_argument(
        "-c", "--cs-id",
        help="Content stream ID (DOC_x for cellar PS, where x is a number; alphanumeric for others)"
    )
    
    # Subcommand: build-request
    req_parser = subparsers.add_parser(
        "build-request",
        help="Build an HTTP request"
    )
    req_parser.add_argument(
        "-r", "--rid",
        required=True,
        help="Resource ID"
    )
    req_parser.add_argument(
        "-t", "--type",
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
        ps = CellarPS.from_string(args.ps)
        
        if args.command == "build-rid":
            rid = CellarResourceId(ps, args.work_id, args.expr_id, args.man_id, args.cs_id)
            print(rid)
        
        elif args.command == "build-request":
            req = Request("")
            rid = CellarResourceId.from_string(args.rid)

            if args.type == "tree-notice":
                req = CellarAPI.tree_notice_request(rid, args.dec_lang)
            elif args.type == "branch-notice":
                req = CellarAPI.branch_notice_request(rid, args.dec_lang, args.acc_lang or "eng")
            elif args.type == "object-notice":
                req = CellarAPI.object_notice_request(rid, args.dec_lang, args.acc_lang, args.alternates)
            elif args.type == "identifiers-notice":
                req = CellarAPI.indentifiers_notice_request(rid)
            elif args.type == "metadata":
                req = CellarAPI.metadata_request(rid, args.dec_lang, args.normalized, args.non_inferred, args.alternates)
            elif args.type == "metadata-tree":
                req = CellarAPI.metadata_tree_request(rid, args.dec_lang, args.normalized, args.non_inferred)
            elif args.type == "content-stream":
                mime_type = getattr(MimeType, args.mime_type.upper())
                req = CellarAPI.content_stream_request(rid, args.dec_lang, mime_type, args.acc_lang or "eng", args.size or MAX_CS_SIZE)
            elif args.type == "content-stream-collection":
                mime_type = getattr(MimeType, args.mime_type.upper())
                collection_type = getattr(CollectionType, args.collection_type.upper())
                req = CellarAPI.content_stream_collection_request(rid, args.dec_lang, collection_type, mime_type, args.acc_lang or "eng")
            else:
                raise ValueError(f"Unsupported request type: {args.type}")
            
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
