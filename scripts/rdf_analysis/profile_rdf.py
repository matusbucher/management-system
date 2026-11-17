"""Profile the Cellar RDF/XML metadata dumps in data/analysis/documents/ and write per-file JSON profiles.

Usage:
    python scripts/rdf_analysis/profile_rdf.py                 # all data/analysis/documents/*.rdf (cached results are reused)
    python scripts/rdf_analysis/profile_rdf.py data/analysis/documents/DORA.rdf    # selected files
    python scripts/rdf_analysis/profile_rdf.py --force         # re-parse even if a profile exists

Output: data/analysis/profile/<name>.json (consumed by classify_predicates.py).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF
from rdflib.term import Node

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdm_ontology import WEMI_ORDER, CdmIndex, load_cdm, short  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "analysis" / "documents"
OUT = ROOT / "data" / "analysis" / "profile"

RES = "http://publications.europa.eu/resource/"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
CELLAR_RE = re.compile(rf"^{re.escape(RES)}cellar/({UUID})(?:\.(\d{{4}})(?:\.(\d{{2}})(?:/(DOC_\d+))?)?)?$")
AXIOM_STRUCTURE = {str(RDF.type), str(OWL.annotatedProperty), str(OWL.annotatedSource), str(OWL.annotatedTarget)}
LANG_EXPR_RE = re.compile(r"\.([A-Z]{3})$")
LANG_MAN_RE = re.compile(r"\.([A-Z]{3})\.([A-Za-z0-9]+)$")


def classify_uri(
    uri: str
) -> tuple[str, str]:
    """
    Classify a URI using only its structure.

    The level is one of work / expression / manifestation / item / vocabulary / other.

    Args:
        uri (str): The URI to classify.

    Returns:
        tuple[str, str]: The URI kind and the URI level.
    """
    m = CELLAR_RE.match(uri)
    if m:
        if m.group(4):
            return "cellar:item", "item"
        if m.group(3):
            return "cellar:manifestation", "manifestation"
        if m.group(2):
            return "cellar:expression", "expression"
        return "cellar:work", "work"
    if uri.startswith(RES):
        rest = uri[len(RES):]
        ps = rest.split("/", 1)[0]
        if ps == "authority":
            parts = rest.split("/")
            return ("authority:table" if len(parts) <= 2 or parts[2] == "" else "authority:entry"), "vocabulary"
        if LANG_MAN_RE.search(rest):
            return f"{ps}:manifestation", "manifestation"
        if LANG_EXPR_RE.search(rest):
            return f"{ps}:expression", "expression"
        return f"{ps}:work-like", "work"
    if uri.startswith("http://eurovoc.europa.eu/"):
        return "eurovoc", "vocabulary"
    host = re.match(r"^https?://([^/]+)", uri)
    return "external:" + (host.group(1) if host else "?"), "other"


def object_kind(
    o: Node
) -> str:
    """
    Classify the object of a triple.

    Args:
        o (Node): The object of the triple.

    Returns:
        str: ``bnode``, a ``literal:...`` kind or ``uri:<uri kind>``.
    """
    if isinstance(o, BNode):
        return "bnode"
    if isinstance(o, Literal):
        if o.language:
            return "literal:lang"
        return "literal:" + (short(str(o.datatype)) if o.datatype else "plain")
    return "uri:" + classify_uri(str(o))[0]


def subject_level(
    g: Graph,
    s: Node,
    cdm: CdmIndex,
    preds: set[str]
) -> tuple[str, str]:
    """
    Infer the WEMI level of a subject.

    Args:
        g (Graph): The RDF graph.
        s (Node): The subject.
        cdm (CdmIndex): The CDM ontology index.
        preds (set[str]): URIs of the predicates used with the subject.

    Returns:
        tuple[str, str]: The level and the evidence it was derived from.
    """
    uri = str(s)
    uri_kind, uri_level = classify_uri(uri)
    if uri_kind.startswith("cellar:"):
        return uri_level, "uri-structure"
    types = {str(o) for o in g.objects(s, RDF.type)}
    type_levels = {l for t in types for l in cdm.class_levels(t) if l in WEMI_ORDER}
    if type_levels:
        return next(l for l in WEMI_ORDER if l in type_levels), "rdf:type"
    if uri_level in ("expression", "manifestation"):
        return uri_level, "uri-suffix"
    if uri_level == "vocabulary":
        return "vocabulary", "uri-structure"
    pred_levels = {l for p in preds if p in cdm.properties for l in cdm.properties[p].domain_levels}
    if pred_levels:
        return next(l for l in WEMI_ORDER if l in pred_levels), "predicate-domain"
    return "untyped", "none"


def profile(
    path: Path
) -> dict:
    """
    Profile one RDF/XML dump: predicate and type usage per WEMI level, axioms, materialised inference and aliases.

    Args:
        path (Path): The RDF/XML file.

    Returns:
        dict: The JSON-serialisable profile of the file.
    """
    cdm = load_cdm()
    t0 = time.time()
    g = Graph()
    g.parse(path, format="xml")
    parse_s = time.time() - t0

    preds_of: dict = defaultdict(set)
    for s, p, _ in g:
        preds_of[s].add(str(p))

    levels: dict = {}
    level_evidence: Counter = Counter()
    uri_kind_subjects: Counter = Counter()
    for s in preds_of:
        if isinstance(s, BNode):
            continue
        uri_kind_subjects[classify_uri(str(s))[0]] += 1
        lvl, ev = subject_level(g, s, cdm, preds_of[s])
        levels[s] = lvl
        level_evidence[(lvl, ev)] += 1

    pred_usage: Counter = Counter()
    type_usage: Counter = Counter()
    for s, p, o in g:
        lvl = "axiom-bnode" if isinstance(s, BNode) else levels[s]
        pred_usage[(lvl, str(p), object_kind(o))] += 1
        if p == RDF.type:
            type_usage[(lvl, str(o))] += 1

    axiom_usage: Counter = Counter()
    axiom_source_level: Counter = Counter()
    for ax in g.subjects(RDF.type, OWL.Axiom):
        src = g.value(ax, OWL.annotatedSource)
        src_level = levels.get(src, "unknown") if src is not None else "unknown"
        axiom_source_level[src_level] += 1
        ap = tuple(sorted(str(o) for o in g.objects(ax, OWL.annotatedProperty)))
        for p in {str(p) for p in g.predicates(ax)} - AXIOM_STRUCTURE:
            axiom_usage[(src_level, ap, p)] += 1

    # materialised inference: super-property / inverse duplicates
    super_dups: Counter = Counter()
    inverse_dups: Counter = Counter()
    pred_set = {p for _, p, _ in g.triples((None, None, None))}
    for p in pred_set:
        info = cdm.properties.get(str(p))
        if not info:
            continue
        supers = cdm.ancestors(str(p))
        inv = info.inverse
        if not supers and not inv:
            continue
        for s, _, o in g.triples((None, p, None)):
            for sup in supers:
                if (s, URIRef(sup), o) in g:
                    super_dups[(str(p), sup)] += 1
            if isinstance(o, (URIRef, BNode)):
                for i in inv:
                    if (o, URIRef(i), s) in g:
                        inverse_dups[(str(p), i)] += 1

    # sameAs equivalence classes (identifier aliases)
    parent: dict = {}

    def find(
        x: Node
    ) -> Node:
        """
        Find the root of an alias group (union-find with path halving).

        Args:
            x (Node): The node to look up.

        Returns:
            Node: The root node of the group.
        """
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for s, o in g.subject_objects(OWL.sameAs):
        parent[find(s)] = find(o)
    groups: dict = defaultdict(set)
    for node in list(parent):
        groups[find(node)].add(node)
    alias_shapes: Counter = Counter()
    group_level_vs_shape: Counter = Counter()
    for members in groups.values():
        kinds = tuple(sorted({classify_uri(str(m))[0].split(":")[0] for m in members}))
        alias_shapes[kinds] += 1
        lv = {levels.get(m) for m in members if m in levels} - {None}
        group_level_vs_shape[(tuple(sorted(lv)), len(members))] += 1

    return {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "parse_seconds": round(parse_s, 1),
        "triples": len(g),
        "subjects_uri": sum(1 for s in preds_of if not isinstance(s, BNode)),
        "subjects_bnode": sum(1 for s in preds_of if isinstance(s, BNode)),
        "distinct_predicates": len(pred_set),
        "uri_kind_subjects": dict(uri_kind_subjects),
        "level_evidence": [[l, e, n] for (l, e), n in level_evidence.items()],
        "pred_usage": [[l, p, ok, n] for (l, p, ok), n in pred_usage.items()],
        "type_usage": [[l, t, n] for (l, t), n in type_usage.items()],
        "axiom_source_level": dict(axiom_source_level),
        "axiom_usage": [[sl, list(ap), p, n] for (sl, ap, p), n in axiom_usage.items()],
        "super_property_duplicates": [[p, s, n] for (p, s), n in super_dups.items()],
        "inverse_duplicates": [[p, i, n] for (p, i), n in inverse_dups.items()],
        "sameas_groups": len(groups),
        "sameas_alias_shapes": [[list(k), n] for k, n in alias_shapes.items()],
        "sameas_group_sizes": [[list(k[0]), k[1], n] for k, n in group_level_vs_shape.items()],
    }


def main() -> None:
    """Profile the selected (or all) RDF dumps and write one JSON profile per file."""
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    files = args.files or sorted(DATA.glob("*.rdf"))
    OUT.mkdir(parents=True, exist_ok=True)
    for f in files:
        target = OUT / (f.stem + ".json")
        if target.exists() and not args.force:
            print(f"[cached] {f.name}")
            continue
        print(f"[parse ] {f.name} ({f.stat().st_size / 1e6:.1f} MB)", flush=True)
        result = profile(f)
        target.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(f"         {result['triples']} triples, parsed in {result['parse_seconds']}s", flush=True)


if __name__ == "__main__":
    main()
