"""Index of the CDM ontology (docs/cdm) used to place RDF terms into the WEMI hierarchy.

The index answers two questions for any CDM class / property:
  * which WEMI level (work / expression / manifestation / item) does it belong to,
  * is it flagged as "Relevant for legal analysis" by the CDM authors.
"""
from __future__ import annotations

from typing import Optional
from dataclasses import dataclass, field

import re
from functools import lru_cache
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

CDM = "http://publications.europa.eu/ontology/cdm#"
CDM_CMR = "http://publications.europa.eu/ontology/cdm/cmr#"
ANNOTATION = "http://publications.europa.eu/ontology/annotation#"

CDM_DIR = Path(__file__).resolve().parents[2] / "docs" / "cdm"
CDM_FILES = ["cdm.rdf", "cdm_annotationproperties.rdf"]

WEMI_ROOTS = {
    CDM + "work": "work",
    CDM + "expression": "expression",
    CDM + "manifestation": "manifestation",
    CDM + "item": "item",
}
WEMI_ORDER = ["work", "expression", "manifestation", "item"]

_LEGAL_RE = re.compile(r"Relevant for legal analysis:\s*(\w+)", re.I)

_PREFIXES = (
    (CDM_CMR, "cmr:"), (CDM, "cdm:"), (ANNOTATION, "annot:"),
    ("http://www.w3.org/2002/07/owl#", "owl:"),
    ("http://www.w3.org/1999/02/22-rdf-syntax-ns#", "rdf:"),
    ("http://www.w3.org/2000/01/rdf-schema#", "rdfs:"),
    ("http://www.w3.org/2004/02/skos/core#", "skos:"),
    ("http://www.w3.org/2001/XMLSchema#", "xsd:"),
)


def short(
    uri: str
) -> str:
    """
    Get the compact prefix form of a URI for tables.

    Args:
        uri (str): The full URI.

    Returns:
        str: The URI with a known namespace replaced by its prefix, or the unchanged URI.
    """
    for ns, prefix in _PREFIXES:
        if uri.startswith(ns):
            return prefix + uri[len(ns):]
    return uri


@dataclass
class PropertyInfo:
    """
    Information about one CDM property.

    Attributes:
        uri (str): The URI of the property.
        label (str): The ``rdfs:label`` of the property.
        kind (str): Kind of the property - object, datatype, annotation or unknown.
        domains (set[str]): URIs of the ``rdfs:domain`` classes.
        ranges (set[str]): URIs of the ``rdfs:range`` classes.
        super_props (set[str]): URIs of the direct super-properties.
        sub_props (set[str]): URIs of the direct sub-properties.
        inverse (set[str]): URIs of the inverse properties.
        legal_flag (Optional[str]): "true" / "false" flag "Relevant for legal analysis", None when the comment has no flag.
        domain_levels (set[str]): WEMI levels of the domain classes.
        range_levels (set[str]): WEMI levels of the range classes.
        level (str): WEMI level of the property - work, expression, manifestation, item, a "+" combination of them,
            generic, other or unknown.
        level_source (str): How the level was determined (domain, domain-non-wemi, super-property of ..., name-prefix,
            no-domain).
    """
    uri: str
    label: str = ""
    kind: str = "unknown"  # object | datatype | annotation | unknown
    domains: set[str] = field(default_factory=set)
    ranges: set[str] = field(default_factory=set)
    super_props: set[str] = field(default_factory=set)  # direct
    sub_props: set[str] = field(default_factory=set)  # direct
    inverse: set[str] = field(default_factory=set)
    legal_flag: Optional[str] = None  # "true" / "false" / None when the comment carries no flag
    domain_levels: set[str] = field(default_factory=set)  # WEMI levels of the domain classes
    range_levels: set[str] = field(default_factory=set)  # WEMI levels of the range classes
    # work | expression | manifestation | item | "work+expression"... | generic | other | unknown
    level: str = "unknown"
    level_source: str = ""


class CdmIndex:
    """
    Index of the CDM ontology: the parsed ontology graph and the properties with their WEMI levels.

    Args:
        cdm_dir (Path): Directory with the CDM ontology files. Default ``docs/cdm``.
        files (Optional[list[str]]): Names of the ontology files to parse. Default None (``CDM_FILES``).
    """

    def __init__(
        self,
        cdm_dir: Path = CDM_DIR,
        files: Optional[list[str]] = None
    ) -> None:
        self.graph = Graph()
        for name in files or CDM_FILES:
            self.graph.parse(cdm_dir / name)
        self._class_levels: dict[str, set[str]] = {}
        self.properties: dict[str, PropertyInfo] = {}
        self._build_properties()

    def class_levels(
        self,
        cls: str
    ) -> set[str]:
        """
        Get the WEMI levels of a class, or {'other:<root>'} for classes outside WEMI (agents, locations...).

        Args:
            cls (str): The URI of the class.

        Returns:
            set[str]: The WEMI levels of the class.
        """
        if cls in self._class_levels:
            return self._class_levels[cls]
        self._class_levels[cls] = set()  # cycle guard
        if cls in WEMI_ROOTS:
            result = {WEMI_ROOTS[cls]}
        else:
            parents = [o for o in self.graph.objects(URIRef(cls), RDFS.subClassOf) if isinstance(o, URIRef)]
            result = set()
            for parent in parents:
                result |= self.class_levels(str(parent))
            if not parents:
                result = {"other:" + short(cls)}
        self._class_levels[cls] = result
        return result

    def wemi_levels_of_classes(
        self,
        classes: set[str]
    ) -> set[str]:
        """
        Get the WEMI levels (work, expression, manifestation, item) of a set of classes.

        Args:
            classes (set[str]): URIs of the classes.

        Returns:
            set[str]: The WEMI levels the classes belong to.
        """
        return {l for c in classes for l in self.class_levels(c) if l in WEMI_ORDER}

    def _build_properties(self) -> None:
        """Collect all CDM properties from the graph and fill in their labels, relations, flags and WEMI levels."""
        g = self.graph
        for t in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property):
            for p in g.subjects(RDF.type, t):
                if not isinstance(p, URIRef):
                    continue
                info = self.properties.setdefault(str(p), PropertyInfo(str(p)))
                if t == OWL.ObjectProperty:
                    info.kind = "object"
                elif t == OWL.DatatypeProperty:
                    info.kind = "datatype"
                elif info.kind == "unknown":
                    info.kind = "annotation"
        for uri, info in self.properties.items():
            p = URIRef(uri)
            labels = list(g.objects(p, RDFS.label))
            info.label = str(labels[0]) if labels else ""
            for c in g.objects(p, RDFS.comment):
                m = _LEGAL_RE.search(str(c))
                if m:
                    info.legal_flag = m.group(1).lower()
            info.domains = {str(o) for o in g.objects(p, RDFS.domain) if isinstance(o, URIRef)}
            info.ranges = {str(o) for o in g.objects(p, RDFS.range) if isinstance(o, URIRef)}
            info.super_props = {str(o) for o in g.objects(p, RDFS.subPropertyOf) if isinstance(o, URIRef)}
            info.inverse = {str(o) for o in g.objects(p, OWL.inverseOf) if isinstance(o, URIRef)}
            info.inverse |= {str(s) for s in g.subjects(OWL.inverseOf, p) if isinstance(s, URIRef)}
            info.domain_levels = self.wemi_levels_of_classes(info.domains)
            info.range_levels = self.wemi_levels_of_classes(info.ranges)
        for uri, info in self.properties.items():
            for sup in info.super_props:
                if sup in self.properties:
                    self.properties[sup].sub_props.add(uri)
        for info in self.properties.values():
            self._assign_level(info)

    def descendants(
        self,
        uri: str
    ) -> set[str]:
        """
        Get all direct and indirect sub-properties of a property.

        Args:
            uri (str): The URI of the property.

        Returns:
            set[str]: URIs of the descendant properties.
        """
        out: set[str] = set()
        stack = [uri]
        while stack:
            info = self.properties.get(stack.pop())
            for sub in info.sub_props if info else ():
                if sub not in out:
                    out.add(sub)
                    stack.append(sub)
        return out

    def ancestors(
        self,
        uri: str
    ) -> set[str]:
        """
        Get all direct and indirect super-properties of a property.

        Args:
            uri (str): The URI of the property.

        Returns:
            set[str]: URIs of the ancestor properties.
        """
        out: set[str] = set()
        stack = [uri]
        while stack:
            info = self.properties.get(stack.pop())
            for sup in info.super_props if info else ():
                if sup not in out:
                    out.add(sup)
                    stack.append(sup)
        return out

    def _assign_level(
        self,
        info: PropertyInfo
    ) -> None:
        """
        Set the WEMI level of a property (and how it was determined) from its domain, sub-properties or name.

        Args:
            info (PropertyInfo): The property to update.
        """
        if info.domain_levels:
            info.level = "+".join(w for w in WEMI_ORDER if w in info.domain_levels)
            info.level_source = "domain"
            return
        if info.domains:  # domain declared but outside WEMI (agent, concept, ...)
            info.level, info.level_source = "other", "domain-non-wemi"
            return
        sub_levels: set[str] = set()
        for sub in self.descendants(info.uri):
            sub_levels |= self.properties[sub].domain_levels
        if sub_levels:
            info.level = "generic"
            info.level_source = "super-property of " + "+".join(w for w in WEMI_ORDER if w in sub_levels)
            return
        m = re.match(r"(work|expression|manifestation|item)_", info.uri.rsplit("#", 1)[-1])
        if m:
            info.level, info.level_source = m.group(1), "name-prefix"
        else:
            info.level, info.level_source = "unknown", "no-domain"


@lru_cache(maxsize=1)
def load_cdm() -> CdmIndex:
    """
    Get the (cached) index of the CDM ontology.

    Returns:
        CdmIndex: The CDM ontology index.
    """
    return CdmIndex()


if __name__ == "__main__":
    from collections import Counter

    idx = load_cdm()
    print(len(idx.properties), "properties")
    print(Counter(p.level for p in idx.properties.values()).most_common())
    print(Counter(p.legal_flag for p in idx.properties.values()))
