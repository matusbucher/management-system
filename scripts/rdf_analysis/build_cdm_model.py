"""Generate src/etlpipe/config/cdm_model.json from the CDM ontology files in data/cdm.

The ETL pipeline needs, at runtime, only three facts about the CDM ontology: the ancestor chain of every property (nearest super-property
first), the WEMI level of every property and the depth/WEMI level of every class. Parsing 1.3 M ontology triples on every run is
wasteful, so this compact model is generated once and committed.

Usage (from the repository root):
    python scripts/rdf_analysis/build_cdm_model.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdm_ontology import CDM, WEMI_ORDER, CdmIndex  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "src" / "etlpipe" / "config" / "cdm_model.json"


def local(
    uri: str
) -> str:
    """
    Get the local name of a URI (the part after ``#``).

    Args:
        uri (str): The URI to extract the local name from.

    Returns:
        str: The local name of the URI.
    """
    return uri.rsplit("#", 1)[-1]


def ordered_chain(
    idx: CdmIndex,
    uri: str
) -> list[str]:
    """
    Get the ancestors of a property, breadth first (nearest super-property first), restricted to known CDM properties.

    Args:
        idx (CdmIndex): The CDM ontology index.
        uri (str): The URI of the property.

    Returns:
        list[str]: Local names of the ancestor properties, nearest first.
    """
    out: list[str] = []
    seen: set[str] = set()
    frontier = [uri]
    while frontier:
        nxt: list[str] = []
        for u in frontier:
            info = idx.properties.get(u)
            for sup in sorted(info.super_props if info else ()):
                if sup in idx.properties and sup not in seen and sup.startswith(CDM):
                    seen.add(sup)
                    out.append(local(sup))
                    nxt.append(sup)
        frontier = nxt
    return out


def class_depths(
    idx: CdmIndex
) -> dict[str, int]:
    """
    Compute the depth of every CDM class in the ``rdfs:subClassOf`` hierarchy (root classes have depth 1).

    Args:
        idx (CdmIndex): The CDM ontology index.

    Returns:
        dict[str, int]: Mapping of class URI to its depth.
    """
    graph = idx.graph
    depth: dict[str, int] = {}

    def d(
        cls: str,
        trail: frozenset[str] = frozenset()
    ) -> int:
        """
        Get the depth of a class, memoised in ``depth``; a cycle in the hierarchy yields 0.

        Args:
            cls (str): The URI of the class.
            trail (frozenset[str]): Classes on the current path, used to detect cycles. Default empty.

        Returns:
            int: The depth of the class.
        """
        if cls in depth:
            return depth[cls]
        if cls in trail:
            return 0
        parents = [str(o) for o in graph.objects(URIRef(cls), RDFS.subClassOf) if isinstance(o, URIRef) and str(o).startswith(CDM)]
        depth[cls] = 1 + max((d(p, trail | {cls}) for p in parents), default=0)
        return depth[cls]

    for c in graph.subjects(RDF.type, OWL.Class):
        if isinstance(c, URIRef) and str(c).startswith(CDM):
            d(str(c))
    return depth


def main() -> None:
    """Generate the compact CDM model JSON and write it to ``OUT``."""
    idx = CdmIndex()
    properties = {}
    for uri, info in idx.properties.items():
        if not uri.startswith(CDM):
            continue
        kind = {"object": "o", "datatype": "d"}.get(info.kind, "a")
        levels = [w for w in WEMI_ORDER if w in info.domain_levels]
        properties[local(uri)] = [kind, levels, ordered_chain(idx, uri)]
    classes = {}
    for uri, depth in class_depths(idx).items():
        levels = [w for w in WEMI_ORDER if w in idx.class_levels(uri)]
        classes[local(uri)] = [depth, levels]
    model = {
        "source": "data/cdm/cdm.rdf + cdm_annotationproperties.rdf",
        "properties": dict(sorted(properties.items())),
        "classes": dict(sorted(classes.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(model, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(properties)} properties, {len(classes)} classes -> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
