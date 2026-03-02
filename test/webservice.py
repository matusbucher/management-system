from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SOAP_ENDPOINT = "https://eur-lex.europa.eu/EURLexWebService"
SOAP_ACTION = "https://eur-lex.europa.eu/EURLexWebService/doQuery"
TEMPLATE_FILE = Path(__file__).with_name("eurlex-search.xml")


def prompt_input(label: str, default: str | None = None, required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        value = input(f"{label}{suffix}: ").strip()

        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""

        print("This field is required.")


def build_soap_payload(template_text: str, values: dict[str, str]) -> str:
    payload = template_text
    for key, value in values.items():
        payload = payload.replace(f"${{{key}}}", value)
    return payload


def call_eurlex_webservice(payload: str) -> str:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Call the EUR-Lex SOAP web service using eurlex-search.xml template."
    )
    parser.add_argument(
        "-f",
        "--request-xml-file",
        dest="request_xml_file",
        help="Path to a full SOAP XML request file to send directly",
    )
    parser.add_argument("-q", "--expert-query", dest="expertquery", help="Value for expertQuery")
    parser.add_argument("-p", "--page", help="Value for page")
    parser.add_argument("-z", "--page-size", dest="pagesize", help="Value for pageSize")
    parser.add_argument("-l", "--search-language", dest="searchlanguage", help="Value for searchLanguage")
    parser.add_argument("-e", "--exclude-all-consleg", dest="excludeallconsleg", help="Value for excludeAllConsleg")
    parser.add_argument("-t", "--limit-to-latest-consleg", dest="limittolatestconsleg", help="Value for limitToLatestConsleg")
    parser.add_argument("-a", "--show-documents-available-in", dest="showdocumentsavailablein", help="Value for showDocumentsAvailableIn")
    parser.add_argument(
        "-o",
        "--save-request-xml",
        dest="save_request_xml",
        help="Optional path where the filled request XML should be saved",
    )
    parser.add_argument(
        "-r",
        "--references-only",
        dest="references_only",
        action="store_true",
        help="Print only <reference> values from the SOAP response",
    )
    return parser.parse_args()


def get_value(cli_value: str | None, label: str, default: str | None = None, required: bool = False) -> str:
    if cli_value is not None and cli_value.strip() != "":
        return cli_value
    return prompt_input(label, default=default, required=required)


def extract_references(response_xml: str) -> list[str]:
    root = ET.fromstring(response_xml)
    references: list[str] = []
    for element in root.iter():
        if element.tag.endswith("reference") and element.text:
            references.append(element.text.strip())
    return references


def main() -> None:
    args = parse_args()

    if args.request_xml_file:
        request_path = Path(args.request_xml_file)
        if not request_path.exists():
            print(f"Request XML file not found: {request_path}")
            return
        payload = request_path.read_text(encoding="utf-8")
    else:
        if not TEMPLATE_FILE.exists():
            print(f"Template file not found: {TEMPLATE_FILE}")
            return

        template_text = TEMPLATE_FILE.read_text(encoding="utf-8")

        print("Provide EUR-Lex search parameters (CLI flags are used directly; only missing values are prompted).")
        values = {
            "expertquery": get_value(args.expertquery, "expert query", required=True),
            "page": get_value(args.page, "page", default="1"),
            "pagesize": get_value(args.pagesize, "page size", default="1"),
            "searchlanguage": get_value(args.searchlanguage, "search language", default="en"),
            "excludeallconsleg": get_value(args.excludeallconsleg, "exclude all consleg (true/false)", default="false"),
            "limittolatestconsleg": get_value(args.limittolatestconsleg, "limit to latest consleg (true/false)", default="false"),
            "showdocumentsavailablein": get_value(args.showdocumentsavailablein, "show documents available in", default="en"),
        }

        payload = build_soap_payload(template_text, values)

        output_request_path = args.save_request_xml
        if output_request_path is None:
            output_request_path = prompt_input("save filled request XML (empty = skip)")
        if output_request_path:
            Path(output_request_path).write_text(payload, encoding="utf-8")
            print(f"Request XML saved to: {output_request_path}")

    try:
        response_xml = call_eurlex_webservice(payload)
        if args.references_only:
            references = extract_references(response_xml)
            if references:
                for reference in references:
                    print(reference)
            else:
                print("No <reference> values found in response.")
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
    main()
