from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


CELLAR_BASE_URL = "https://publications.europa.eu/resource/cellar"

REFERENCE_PATTERN = re.compile(
	r"^(?P<prefix_lang>[a-zA-Z]{3})_cellar:(?P<cellar_id>[0-9a-fA-F\-]+)_(?P<suffix_lang>[a-zA-Z]{2,3})$"
)
UUID_PATTERN = re.compile(
	r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

NOTICE_ALIASES = {
	"tree": "tree",
	"tree-notice": "tree",
	"branch": "branch",
	"branch-notice": "branch",
	"object": "object",
	"object-notice": "object",
	"identifier": "identifier",
	"identifier-notice": "identifier",
	"rdf": "rdf",
	"rdf-notice": "rdf",
}


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


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Request documents from CELLAR API using a CELLAR reference or CELLAR id."
	)
	parser.add_argument(
		"-r",
		"--reference",
		help="Reference in format like eng_cellar:7efd4d98-76f7-11e9-9f05-01aa75ed71a1_en",
	)
	parser.add_argument(
		"-i",
		"--cellar-id",
		dest="cellar_id",
		help="Raw CELLAR UUID, e.g. 7efd4d98-76f7-11e9-9f05-01aa75ed71a1",
	)
	parser.add_argument(
		"-n",
		"--notice-type",
		dest="notice_type",
		help="Notice type: tree, branch, object, identifier, rdf (also accepts *-notice aliases)",
	)
	parser.add_argument(
		"-l",
		"--language",
		help="Language query parameter (default: eng; inferred from reference prefix when possible)",
	)
	parser.add_argument(
		"output_file",
		help="Output file path where CELLAR response body will be saved",
	)
	return parser.parse_args()


def get_value(cli_value: str | None, label: str, default: str | None = None, required: bool = False) -> str:
	if cli_value is not None and cli_value.strip() != "":
		return cli_value
	return prompt_input(label, default=default, required=required)


def normalize_notice_type(value: str) -> str:
	normalized = value.strip().lower()
	if normalized not in NOTICE_ALIASES:
		accepted = ", ".join(sorted(NOTICE_ALIASES.keys()))
		raise ValueError(f"Invalid notice type '{value}'. Allowed values: {accepted}")
	return NOTICE_ALIASES[normalized]


def parse_reference(reference: str) -> tuple[str, str]:
	match = REFERENCE_PATTERN.match(reference.strip())
	if not match:
		raise ValueError(
			"Invalid reference format. Expected format like: "
			"eng_cellar:7efd4d98-76f7-11e9-9f05-01aa75ed71a1_en"
		)

	return match.group("cellar_id"), match.group("prefix_lang").lower()


def build_request_from_input(reference: str | None, cellar_id: str | None, language: str | None) -> tuple[str, str]:
	if reference:
		parsed_cellar_id, inferred_language = parse_reference(reference)
		final_language = language if language else inferred_language
		return parsed_cellar_id, final_language

	if not cellar_id:
		raise ValueError("Either reference or cellar-id must be provided.")

	final_cellar_id = cellar_id.strip()
	if not UUID_PATTERN.match(final_cellar_id):
		raise ValueError(
			"Invalid CELLAR id format. Expected UUID like: 7efd4d98-76f7-11e9-9f05-01aa75ed71a1"
		)

	final_language = language if language else "eng"
	return final_cellar_id, final_language


def build_accept_header(notice_type: str) -> str:
	if notice_type == "rdf":
		return "application/rdf+xml"
	return f"application/xml;notice={notice_type}"


def call_cellar_api(cellar_id: str, notice_type: str, language: str) -> str:
	query = urlencode({"language": language})
	url = f"{CELLAR_BASE_URL}/{cellar_id}?{query}"
	headers = {
		"Accept": build_accept_header(notice_type),
	}
	request = Request(url=url, headers=headers, method="GET")

	with urlopen(request, timeout=60) as response:
		return response.read().decode("utf-8", errors="replace")


def main() -> None:
	args = parse_args()

	try:
		reference = get_value(args.reference, "reference (empty to use cellar id)", required=False)
		raw_cellar_id = None
		if not reference:
			raw_cellar_id = get_value(args.cellar_id, "cellar id", required=True)

		notice_type_raw = get_value(
			args.notice_type,
			"notice type (tree/branch/object/identifier/rdf)",
			default="tree",
			required=True,
		)
		notice_type = normalize_notice_type(notice_type_raw)

		language = args.language.strip().lower() if args.language else None
		cellar_id, final_language = build_request_from_input(reference, raw_cellar_id, language)

		print("\n--- CELLAR Request ---")
		print(f"cellar_id: {cellar_id}")
		print(f"notice_type: {notice_type}")
		print(f"language: {final_language}")
		print(f"accept: {build_accept_header(notice_type)}")

		response_text = call_cellar_api(cellar_id, notice_type, final_language)
		output_path = Path(args.output_file)
		output_path.parent.mkdir(parents=True, exist_ok=True)
		output_path.write_text(response_text, encoding="utf-8")
		print(f"Response saved to: {output_path}")
	except HTTPError as error:
		error_body = error.read().decode("utf-8", errors="replace")
		print(f"HTTP error: {error.code} {error.reason}")
		print("\n--- Error response body ---")
		print(error_body)
	except URLError as error:
		print(f"Connection error: {error.reason}")
	except ValueError as error:
		print(f"Input error: {error}")
	except Exception as error:
		print(f"Unexpected error: {error}")


if __name__ == "__main__":
	main()
