from enum import Enum


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
    "isl": "is",
    "ita": "it",
    "lav": "lv",
    "lit": "lt",
    "mlt": "mt",
    "nld": "nl",
    "nor": "no",
    "pol": "pl",
    "por": "pt",
    "ron": "ro",
    "slk": "sk",
    "slv": "sl",
    "spa": "es",
    "swe": "sv",
}

MANIFESTATION_FORMATS = ("pdf", "html", "xml", "fmx", "fmx4")


class MimeType(Enum):
    """MIME types for different document formats."""
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
    """Types of content stream collection formats."""
    LIST = "list"
    ZIP = "zip"