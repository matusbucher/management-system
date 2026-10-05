import re
from pathlib import Path

from enum import Enum

########## WEBSERVICE ##########

SOAP_ENDPOINT = "https://eur-lex.europa.eu/EURLexWebService"
SOAP_ACTION = "https://eur-lex.europa.eu/EURLexWebService/doQuery"
TEMPLATE_FILENAME = "templates/eurlex-search.xml"

AVAILABLE_IN_TAG = "sear:showDocumentsAvailableIn"


########## CELLAR ##########

RESOURCE_BASE_URL = "https://publications.europa.eu/resource"
WEBAPI_BASE_URL = "https://publications.europa.eu/webapi"

ISO_639_3_CODES = {
    "BUL": "Bulgarian",
    "CES": "Czech",
    "DAN": "Danish",
    "DEU": "German",
    "ELL": "Modern Greek",
    "ENG": "English",
    "EST": "Estonian",
    "FIN": "Finnish",
    "FRA": "French",
    "GLE": "Irish",
    "HRV": "Croatian",
    "HUN": "Hungarian",
    "ISL": "Icelandic",
    "ITA": "Italian",
    "LAV": "Latvian",
    "LIT": "Lithuanian",
    "MLT": "Maltese",
    "NLD": "Dutch",
    "NOR": "Norwegian",
    "POL": "Polish",
    "POR": "Portuguese",
    "RON": "Romanian, Moldavian, Moldovan",
    "SLK": "Slovak",
    "SLV": "Slovene",
    "SPA": "Spanish, Castillian",
    "SWE": "Swedish",
}

MANIFESTATION_FORMATS = ["pdf", "html", "xml", "fmx", "fmx4"]

UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

CELLAR_EXPR_ID_PATTERN = re.compile(r"^\d{4}$")
CELLAR_MAN_ID_PATTERN = re.compile(r"^\d{2}$")
CELLAR_CS_ID_PATTERN = re.compile(r"^DOC_\d+$")

MAX_CS_SIZE = 9223372036854775807 # 2^63 - 1


class CellarPS(Enum):
    CELLAR = "cellar"
    CELLEX = "cellex"
    OJ = "oj"
    COM = "com"
    GENPUB = "genpub"
    EP = "ep"
    JURISPRUDENCE = "jurisprudence"
    DD = "dd"
    MTF = "mtf"
    CONSOLIDATION = "consolidation"
    EUROSTAT = "eurostat"
    EESC = "eesc"
    COR = "cor"
    NIM = "nim"
    PEGASE = "pegase"
    TRANSJAI = "transjai"
    AGENT = "agent"
    URISERV = "uriserv"
    JOIN = "join"
    SWD = "swd"
    COMNAT = "comnat"
    MDR = "mdr"
    LEGISSUM = "legissum"
    ECLI = "ecli"
    PROCEDURE = "procedure"
    PROCEDURE_EVENT = "procedure-event"
    ELI = "eli"
    IMMC = "immc"
    PLANJO = "planjo"


class MimeType(Enum):
    PDF1X = "application/pdf;type=pdf1x"
    XHTML_XML = "application/xhtml+xml"
    XHTML_XML_SIMPLIFIED = "application/xhtml+xml;type=simplified"
    XML = "application/xml"
    SGML_FMX3 = "text/sgml;type=fmx3"
    XML_FMX3 = "application/xml;type=fmx3"
    HTML = "text/html"
    HTML_SIMPLIFIED = "text/html;type=simplified"
    PLAIN_TEXT = "text/plain"
    MSWORD = "application/msword"
    PDF = "application/pdf"
    PDF_PDFA1A = "application/pdf;type=pdfa1a"
    PDF_PDFA1B = "application/pdf;type=pdfa1b"
    PDF_PDFX = "application/pdf;type=pdfx"
    EBOOK_AMAZON = "application/vnd.amazon.ebook"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    EPUB = "application/epub+zip"
    SGML_FMX2 = "text/sgml;type=fmx2"
    XML_FMX2 = "application/xml;type=fmx2"
    XML_FMX4 = "application/xml;type=fmx4"
    JPEG = "image/jpeg"
    MOBI = "application/x-mobipocket-ebook"
    PPTX_SLIDESHOW = "application/vnd.openxmlformats-officedocument.presentationml.slideshow"
    PPT = "application/vnd.ms-powerpoint"
    PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    RDF_XML = "application/rdf+xml"
    RTF = "text/rtf"
    SGML = "text/sgml"
    SPARQL_QUERY = "application/sparql-query"
    SPARQL_RESULTS = "application/sparql-results+xml"
    TIFF_FX = "image/tiff-fx"
    TIFF = "image/tiff"
    XLS = "application/vnd.ms-excel"
    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    XSLT = "application/xslt+xml"
    ZIP = "application/zip"
    GIF = "image/gif"
    PNG = "image/png"
    GZIP = "application/x-gzip"


class CollectionType(Enum):
    LIST = "list"
    ZIP = "zip"


########## NEO4J DATABASE LOADER ##########

class GraphNodeLabel(Enum):
    """Neo4j node labels for the database schema."""
    DOCUMENT = "Document"
    DOCUMENT_VERSION = "DocumentVersion"
    DOCUMENT_FORMAT = "DocumentFormat"
    DOCUMENT_FILE = "DocumentFile"
    LANGUAGE = "Language"


class GraphProperty(Enum):
    """Neo4j node properties for the database schema."""
    # Common properties
    CELLAR_ID = "cellar_id"
    CELLAR_URI = "cellar_uri"
    CREATED_DATE = "created_date"
    MODIFIED_DATE = "modified_date"
    TITLE = "title"
    
    # Document properties
    DOCUMENT_TYPE = "document_type"
    
    # Version properties
    VERSION_ID = "version_id"
    SUBTITLE = "subtitle"
    LANGUAGE = "language"
    LANGUAGE_ISO_639_1 = "language_iso_639_1"
    
    # Format properties
    FORMAT_ID = "format_id"
    FORMAT_TYPE = "format_type"
    CONTENT_FORMAT = "content_format"
    
    # OJ (Official Journal) properties
    OJ_VOLUME = "oj_volume"
    OJ_SECTION = "oj_section"
    OJ_PAGE_FIRST = "oj_page_first"
    OJ_PAGE_LAST = "oj_page_last"
    OJ_NATURAL_NUMBER = "oj_natural_number"
    
    # File properties
    FILE_ID = "file_id"
    MIME_TYPE = "mime_type"
    
    # Language properties
    CODE_ISO_639_3 = "code_iso_639_3"


class GraphRelationship(Enum):
    """Neo4j relationship types for the database schema."""
    HAS_VERSION = "HAS_VERSION"
    HAS_FORMAT = "HAS_FORMAT"
    HAS_FILE = "HAS_FILE"


class LoaderStatKey(Enum):
    """Keys for loader statistics tracking."""
    DOCUMENTS = "documents"
    VERSIONS = "versions"
    FORMATS = "formats"
    FILES = "files"
    ERRORS = "errors"


class OJPropertyKey:
    """Official Journal property keys in RDF metadata."""
    VOLUME = "manifestation_official-journal_part_volume_oj"
    SECTION = "manifestation_official-journal_part_section_oj"
    PAGE_FIRST = "manifestation_official-journal_part_page_first"
    PAGE_LAST = "manifestation_official-journal_part_page_last"
    NATURAL_NUMBER = "manifestation_official-journal_part_natural_number"


ISO_639_3_TO_639_1 = {
    "bul": "bg",
    "ces": "cs",
    "dan": "da",
    "deu": "de",
    "ell": "el",
    "eng": "en",
    "est": "et",
    "fin": "fi",
    "fra": "fr",
    "gle": "ga",
    "hrv": "hr",
    "hun": "hu",
    "ita": "it",
    "lav": "lv",
    "lit": "lt",
    "mlt": "mt",
    "nld": "nl",
    "pol": "pl",
    "por": "pt",
    "ron": "ro",
    "slk": "sk",
    "slv": "sl",
    "spa": "es",
    "swe": "sv",
}

DEFAULT_TITLE = "Untitled"
DEFAULT_VALUE = "unknown"

CELLAR_BASE_URI = "http://publications.europa.eu/resource/cellar/"

NEO4J_CONSTRAINTS = [
    "CREATE CONSTRAINT document_cellar_id IF NOT EXISTS ON (d:Document) ASSERT d.cellar_id IS UNIQUE",
    "CREATE CONSTRAINT version_cellar_uri IF NOT EXISTS ON (v:DocumentVersion) ASSERT v.cellar_uri IS UNIQUE",
    "CREATE CONSTRAINT format_cellar_uri IF NOT EXISTS ON (f:DocumentFormat) ASSERT f.cellar_uri IS UNIQUE",
    "CREATE CONSTRAINT file_cellar_uri IF NOT EXISTS ON (fi:DocumentFile) ASSERT fi.cellar_uri IS UNIQUE",
    "CREATE CONSTRAINT language_code IF NOT EXISTS ON (l:Language) ASSERT l.code_iso_639_3 IS UNIQUE",
]

NEO4J_INDEXES = [
    "CREATE INDEX document_title IF NOT EXISTS FOR (d:Document) ON (d.title)",
    "CREATE INDEX document_type IF NOT EXISTS FOR (d:Document) ON (d.document_type)",
    "CREATE INDEX version_language IF NOT EXISTS FOR (v:DocumentVersion) ON (v.language)",
    "CREATE INDEX file_mime_type IF NOT EXISTS FOR (f:DocumentFile) ON (f.mime_type)",
]


########## WEMI HIERARCHY LEVELS ##########

class WEMILevel(Enum):
    """WEMI hierarchy levels for document loading.
    
    WEMI = Work, Expression, Manifestation, Item
    """
    WORK = "work"
    EXPRESSION = "expression"
    MANIFESTATION = "manifestation"
    ITEM = "item"


# Default WEMI levels to load (Work only)
DEFAULT_WEMI_LEVELS = {WEMILevel.WORK}

# All WEMI levels
ALL_WEMI_LEVELS = {WEMILevel.WORK, WEMILevel.EXPRESSION, WEMILevel.MANIFESTATION, WEMILevel.ITEM}


########## RDF PARSER ##########

# Namespace mappings for EURLex RDF
EURLEX_RDF_NAMESPACES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "cdm": "http://publications.europa.eu/ontology/cdm#",
    "annotation": "http://publications.europa.eu/ontology/annotation#",
    "cmr": "http://publications.europa.eu/ontology/cdm/cmr#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "xml": "http://www.w3.org/XML/1998/namespace",
}

# RDF/XML Element Names
class RDFElement(Enum):
    """RDF/XML element names for parsing."""
    DESCRIPTION = "Description"
    TYPE = "type"
    RESOURCE = "resource"
    ABOUT = "about"
    SAME_AS = "sameAs"


# RDF Property Names
class RDFProperty(Enum):
    """RDF property names used in CDM ontology."""
    # CMR properties
    CREATION_DATE = "creationDate"
    LAST_MODIFICATION_DATE = "lastModificationDate"
    LANG = "lang"
    MANIFESTATION_MIME_TYPE = "manifestationMimeType"
    
    # CDM properties
    EXPRESSION_TITLE = "expression_title"
    EXPRESSION_SUBTITLE = "expression_subtitle"
    EXPRESSION_BELONGS_TO_WORK = "expression_belongs_to_work"
    EXPRESSION_USES_LANGUAGE = "expression_uses_language"
    MANIFESTATION_TYPE = "manifestation_type"
    MANIFESTATION_MANIFESTS_EXPRESSION = "manifestation_manifests_expression"
    MANIFESTATION_PART_OF_MANIFESTATION = "manifestation_part_of_manifestation"
    ITEM_IDENTIFIER = "item_identifier"
    ITEM_BELONGS_TO_MANIFESTATION = "item_belongs_to_manifestation"
    
    # OWL properties
    ANNOTATED_SOURCE = "annotatedSource"
    ANNOTATED_TARGET = "annotatedTarget"
    ANNOTATED_PROPERTY = "annotatedProperty"
    
    # Annotation properties
    START_OF_VALIDITY = "start_of_validity"
    COMMENT_ON_DATE = "comment_on_date"
    TYPE_OF_LINK_TARGET = "type_of_link_target"


# Resource Type Identifiers
class ResourceType:
    """Resource type identifiers found in rdf:type URIs."""
    ITEM = "item"
    MANIFESTATION = "manifestation"
    EXPRESSION = "expression"
    WORK = "work"
    AXIOM = "Axiom"


# Validation patterns
UUID_PATTERN_LENGTH = 36
UUID_PATTERN_DASH_COUNT = 4
LANGUAGE_CODE_LENGTH = 3

# URI patterns
LANGUAGE_URI_MARKER = "language/"
URI_PART_SEPARATOR = "."
URI_PATH_SEPARATOR = "/"
PROPERTY_NAMESPACE_MARKER = "#"
