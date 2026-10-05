import sys
from pathlib import Path

from urllib.request import urlopen
from urllib.error import HTTPError

workspace_root = Path(__file__).parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from etl.cellar_api import *
from src.etl.constants import *

# Fill in the ps_id components for your target document
WORK_ID = "35e93bb4-8905-11e9-9369-01aa75ed71a1"
EXPR_ID = "0006"
MAN_ID  = "02"
CS_ID   = "DOC_3"

ps_id_fmx = CellarAPI.cellar_ps_id(WORK_ID, EXPR_ID, MAN_ID, CS_ID)
ps_id_xml = CellarAPI.cellar_ps_id(WORK_ID, EXPR_ID)
ps_id_pdf = CellarAPI.cellar_ps_id(WORK_ID, EXPR_ID)
ps_id_tree = CellarAPI.cellar_ps_id(WORK_ID)

req_fmx = CellarAPI.content_stream_request(CellarPS.CELLAR, ps_id_fmx, mime_type=MimeType.XML_FMX4)
req_xml = CellarAPI.content_stream_request(CellarPS.CELLAR, ps_id_xml, mime_type=MimeType.XHTML_XML)
req_pdf = CellarAPI.content_stream_request(CellarPS.CELLAR, ps_id_pdf, mime_type=MimeType.PDF)
req_tree = CellarAPI.metadata_tree_request(CellarPS.CELLAR, ps_id_tree, normalized=True, non_inferred=True)
req = req_tree

try:
    with urlopen(req) as response:
        data = response.read()
    print(f"Downloaded {len(data)} bytes (status {response.status})")
    with open("tmp/test_output.xml", "wb") as f:
        f.write(data)
    print("Saved to tmp/test_output.xml")
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
