"""Show what each tmp/*.rdf dump says about its *focal* resource (the Cellar ID requested in test/cellar_base.py).

Answers: is the file really about the intended act, which aliases does it have, which predicates have the
focal work as subject (its own attributes) and how many relations point at it.

Usage: python scripts/rdf_analysis/inspect_focal.py [--json out.json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdm_ontology import short  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CELLAR = "http://publications.europa.eu/resource/cellar/"


def load_documents() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("cellar_base", ROOT / "test" / "cellar_base.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DOCUMENTS


def alias_group(g: Graph, start: URIRef) -> set[URIRef]:
    seen, stack = {start}, [start]
    while stack:
        node = stack.pop()
        for other in list(g.objects(node, OWL.sameAs)) + list(g.subjects(OWL.sameAs, node)):
            if other not in seen:
                seen.add(other)
                stack.append(other)
    return seen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    report = {}
    for name, uuid in load_documents().items():
        path = ROOT / "tmp" / f"{name}.rdf"
        if not path.exists():
            continue
        g = Graph()
        g.parse(path, format="xml")
        focal = URIRef(CELLAR + uuid)
        group = alias_group(g, focal)
        own = Counter()
        incoming = Counter()
        types: set[str] = set()
        for member in group:
            for p, o in g.predicate_objects(member):
                own[short(str(p))] += 1
                if p == RDF.type:
                    types.add(short(str(o)))
            for _, p in g.subject_predicates(member):
                incoming[short(str(p))] += 1
        celex = sorted(str(m).rsplit("/", 1)[-1] for m in group if "/celex/" in str(m))
        report[name] = {
            "cellar_id": uuid,
            "triples": len(g),
            "aliases": sorted(str(m).replace("http://publications.europa.eu/resource/", "") for m in group),
            "celex": celex,
            "types": sorted(types),
            "own_triples": sum(own.values()),
            "own_predicates": dict(own.most_common()),
            "incoming_triples": sum(incoming.values()),
            "incoming_top": dict(incoming.most_common(8)),
        }
        r = report[name]
        print(f"{name:48s} celex={','.join(celex) or '-':22s} triples={r['triples']:7d} own={r['own_triples']:3d} "
              f"incoming={r['incoming_triples']:6d} aliases={len(group)}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
