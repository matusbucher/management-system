import sys
from pathlib import Path

from urllib.request import urlopen
from urllib.error import HTTPError

workspace_root = Path(__file__).parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from src.eurlex.cellar_api import CellarResourceId, CellarAPI
from src.eurlex.constants import CellarPS, MimeType

WORK_ID = "35e93bb4-8905-11e9-9369-01aa75ed71a1"
EXPR_ID = "0006"
MAN_ID  = "02"
CS_ID   = "DOC_3"

id_work = CellarResourceId(CellarPS.CELLAR, WORK_ID)
id_expr = CellarResourceId(CellarPS.CELLAR, WORK_ID, EXPR_ID)
id_item = CellarResourceId(CellarPS.CELLAR, WORK_ID, EXPR_ID, MAN_ID, CS_ID)

req_fmx = CellarAPI.content_stream_request(id_item, mime_type=MimeType.XML_FMX4)
req_xml = CellarAPI.content_stream_request(id_expr, mime_type=MimeType.XHTML_XML)
req_pdf = CellarAPI.content_stream_request(id_expr, mime_type=MimeType.PDF)

req_rdf_expr = CellarAPI.metadata_request(id_expr)
req_rdf_work = CellarAPI.metadata_request(id_work)

req_rdf_tree = CellarAPI.metadata_tree_request(id_work, normalized=True, non_inferred=True)


if __name__ == "__main__":
    req = req_rdf_work
    try:
        with urlopen(req) as response:
            data = response.read()
        print(f"Downloaded {len(data)} bytes (status {response.status})")
        with open("tmp/test_output.rdf", "wb") as f:
            f.write(data)
        print("Saved to tmp/test_output.rdf")
    except HTTPError as e:
        error_body = e.read()
        print(f"HTTP error {e.code}: {e.reason}")
        print("\n--- Error response headers ---")
        print(e.headers)
        print("--- Error response body ---")
        try:
            print(error_body.decode("utf-8"))
        except UnicodeDecodeError:
            print(error_body.decode("utf-8", errors="replace"))
