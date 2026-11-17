"""
Classification of Cellar resource URIs by their structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote
from typing import Optional

from frozendict import frozendict

from .constants import RESOURCE_BASE

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_CELLAR_RE = re.compile(rf"^{re.escape(RESOURCE_BASE)}cellar/({_UUID})(?:\.(\d{{4}})(?:\.(\d{{2}})(?:/(DOC_\d+))?)?)?$")
_LANG_EXPRESSION_RE = re.compile(r"\.([A-Z]{3})$")
_LANG_MANIFESTATION_RE = re.compile(r"\.([A-Z]{3})\.([A-Za-z0-9]+)$")

EUROVOC_PREFIX = "http://eurovoc.europa.eu/"
ELI_PREFIX = "http://data.europa.eu/eli/"

LEVEL_WORK = "work"
LEVEL_EXPRESSION = "expression"
LEVEL_MANIFESTATION = "manifestation"
LEVEL_ITEM = "item"
LEVEL_CONCEPT = "concept"
LEVEL_INSTITUTION = "institution"
LEVEL_OTHER = "other"

# first character of a CELEX number = sector
_CELEX_SECTOR_KIND = frozendict({
    "0": "consolidated",
    "1": "treaty",
    "2": "agreement",
    "3": "legislation",
    "4": "complementary",
    "5": "preparatory",
    "6": "case-law",
    "7": "national-measure",
    "8": "national-case-law",
    "9": "parliamentary",
    "C": "oj-c",
    "E": "efta",
})


@dataclass(frozen=True)
class UriInfo:
    """
    Classification of a resource URI.

    Attributes:
        scheme (str): URI scheme - cellar, celex, oj, eli, comnat, authority, eurovoc, ... or "external".
        level (str): WEMI level or reference-data kind - work / expression / manifestation / item / concept /
            institution / other.
        local (str): Path after the scheme (authority: "<table>/<code>"). Default "".
    """
    scheme: str  # cellar, celex, oj, eli, comnat, authority, eurovoc, ... or "external"
    level: str  # work / expression / manifestation / item / concept / institution / other
    local: str = ""  # path after the scheme (authority: "<table>/<code>")


def classify_uri(
    uri: str
) -> UriInfo:
    """
    Classify a URI into (scheme, WEMI level or reference-data kind) using only its structure.

    Args:
        uri (str): The URI to classify.

    Returns:
        UriInfo: The scheme, level and local part of the URI.
    """
    m = _CELLAR_RE.match(uri)
    if m:
        if m.group(4):
            return UriInfo("cellar", LEVEL_ITEM, m.group(1))
        if m.group(3):
            return UriInfo("cellar", LEVEL_MANIFESTATION, m.group(1))
        if m.group(2):
            return UriInfo("cellar", LEVEL_EXPRESSION, m.group(1))
        return UriInfo("cellar", LEVEL_WORK, m.group(1))
    if uri.startswith(RESOURCE_BASE):
        rest = uri[len(RESOURCE_BASE):]
        scheme, _, path = rest.partition("/")
        if scheme == "authority":
            level = LEVEL_INSTITUTION if path.startswith("corporate-body/") else LEVEL_CONCEPT
            return UriInfo("authority", level, path)
        if _is_lifecycle_scheme(scheme, path):  # events of a dossier end in ``_PUB_OJ`` or a date - never a language suffix
            return UriInfo(scheme, LEVEL_WORK, path)
        if _LANG_MANIFESTATION_RE.search(path):
            return UriInfo(scheme, LEVEL_MANIFESTATION, path)
        if _LANG_EXPRESSION_RE.search(path):
            return UriInfo(scheme, LEVEL_EXPRESSION, path)
        return UriInfo(scheme, LEVEL_WORK, path)
    if uri.startswith(EUROVOC_PREFIX):
        return UriInfo("eurovoc", LEVEL_CONCEPT, uri[len(EUROVOC_PREFIX):])
    return UriInfo("external", LEVEL_OTHER, uri)


# ---- lifecycle entities: dossiers (procedures) and their events ----------------------------------------------------------
_DOSSIER_SCHEMES = frozenset({"procedure", "dossier", "internal_proc", "intproc", "case", "session"})
_EVENT_SCHEMES = frozenset({"procedure-event", "internal_proc-event", "intproc-event", "case-event", "session-sitting"})

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_BODY_SUFFIX = re.compile(r"_by([A-Za-z0-9]+)$")
_ID_KEY = frozendict({"case": "caseId", "case-event": "caseId", "session": "sessionId", "session-sitting": "sessionId"})


_PEGASE_EVENT = re.compile(r"\.\d{4}-\d{2}-\d{2}_")


def _is_lifecycle_scheme(
    scheme: str,
    path: str
) -> bool:
    """
    Determine if a URI scheme (with its path) denotes a lifecycle entity - a dossier or an event.

    Args:
        scheme (str): The URI scheme.
        path (str): The path after the scheme.

    Returns:
        bool: True if the scheme denotes a dossier or an event, False otherwise.
    """
    return (scheme in _DOSSIER_SCHEMES or scheme in _EVENT_SCHEMES or scheme.endswith("-event")
            or (scheme == "pegase" and bool(_PEGASE_EVENT.search(path))))


def lifecycle_kind(
    uri: str
) -> Optional[str]:
    """
    Get the lifecycle kind from the URI scheme (``procedure/…``, ``procedure-event/…``).

    Args:
        uri (str): The URI to inspect.

    Returns:
        Optional[str]: ``"dossier"`` or ``"event"``, None for anything else.
    """
    info = classify_uri(uri)
    if info.scheme in _EVENT_SCHEMES or info.scheme.endswith("-event") or (info.scheme == "pegase" and _PEGASE_EVENT.search(info.local)):
        return "event"
    if info.scheme in _DOSSIER_SCHEMES:
        return "dossier"
    return None


def event_attributes(
    uri: str
) -> dict[str, str]:
    """
    Get what the URI of an event says about it (the dumps carry no literals on events).

    * ``procedure-event/2020_359.2022-12-27_PUB_OJ``         -> procedureId 2020_359, eventDate 2022-12-27, eventCode PUB_OJ
    * ``procedure-event/2025_404.2025-12-17_ADP_PROPLEG_byCOM`` -> eventCode ADP_PROPLEG, byBody COM
    * ``case-event/C-245%2F25.CC_NC_PUB_OJ_2026-01-26``      -> caseId C-245/25, eventCode CC_NC_PUB_OJ, eventDate 2026-01-26

    Args:
        uri (str): The URI of the event.

    Returns:
        dict[str, str]: The attributes found in the URI (procedureId / caseId / sessionId, eventDate, byBody, eventCode).
    """
    info = classify_uri(uri)
    local = unquote(info.local)
    out: dict[str, str] = {}
    head, dot, rest = local.partition(".")
    if dot:
        out[_ID_KEY.get(info.scheme, "procedureId")] = head
    else:
        rest = local
    m = _ISO_DATE.search(rest)
    if m:
        out["eventDate"] = m.group(0)
        rest = rest[:m.start()] + rest[m.end():]
    rest = rest.strip("._")
    b = _BODY_SUFFIX.search(rest)
    if b:
        out["byBody"] = b.group(1)
        rest = rest[:b.start()].strip("._")
    if re.search(r"[A-Za-z]", rest):  # a bare number (sitting number) is not an event code
        out["eventCode"] = rest
    return out


def dossier_attributes(
    uri: str
) -> dict[str, str]:
    """
    Get the identifier of a dossier from its URI.

    ``procedure/2020_359`` -> procedureId 2020_359 (``case/…`` -> caseId, ``session/…`` -> sessionId).

    Args:
        uri (str): The URI of the dossier.

    Returns:
        dict[str, str]: The identifier attribute of the dossier; empty when the URI has no local part.
    """
    info = classify_uri(uri)
    return {_ID_KEY.get(info.scheme, "procedureId"): unquote(info.local)} if info.local else {}


def is_structural_cellar(
    uri: str
) -> bool:
    """
    Determine if a URI is a Cellar ``<uuid>.NNNN…`` URI.

    It looks like an expression but is how Cellar numbers the events of a dossier and the sittings of a session.

    Args:
        uri (str): The URI to check.

    Returns:
        bool: True if the URI is a Cellar URI below the work level, False otherwise.
    """
    info = classify_uri(uri)
    return info.scheme == "cellar" and info.level != LEVEL_WORK


def identifiers_of(
    uri: str
) -> dict[str, str]:
    """
    Get the identifier carried by a work URI itself, e.g. {"celex": "32022L2555"}.

    Args:
        uri (str): The URI to inspect.

    Returns:
        dict[str, str]: The identifier by kind (cellarId, celex, ojId, eli); empty for other URI kinds.
    """
    info = classify_uri(uri)
    if info.level != LEVEL_WORK:
        return {}
    if info.scheme == "cellar":
        return {"cellarId": info.local}
    if info.scheme == "celex":
        return {"celex": unquote(info.local)}
    if info.scheme == "oj":
        return {"ojId": unquote(info.local)}
    if info.scheme == "eli":
        return {"eli": ELI_PREFIX + info.local}
    return {}


def celex_source_kind(
    celex: Optional[str]
) -> str:
    """
    Get the document kind from the CELEX sector (legislation, preparatory, case-law ...).

    Args:
        celex (Optional[str]): The CELEX number.

    Returns:
        str: The document kind; "unknown" when there is no CELEX number, "other" for an unknown sector.
    """
    if not celex:
        return "unknown"
    return _CELEX_SECTOR_KIND.get(celex[0], "other")


# CELEX type letter of sector 3 (legislation) -> CDM class name; used when the dump carries no specific class
_CELEX_LEGISLATION_TYPE = frozendict({"R": "regulation", "L": "directive", "D": "decision", "H": "recommendation"})


def celex_doc_type(
    celex: Optional[str]
) -> Optional[str]:
    """
    Get the document type derived from a CELEX number such as ``32022R2554`` (regulation).

    Args:
        celex (Optional[str]): The CELEX number.

    Returns:
        Optional[str]: The document type; None when it cannot be told.
    """
    if celex and len(celex) >= 6 and celex[0] == "3":
        return _CELEX_LEGISLATION_TYPE.get(celex[5])
    return None