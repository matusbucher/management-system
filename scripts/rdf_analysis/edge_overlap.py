"""Quantify how much of the relation graph survives de-duplication, and how much overlap there is between files.

Steps per file:
  1. resolve owl:sameAs alias groups into one canonical resource (CELEX > Cellar UUID > first URI);
  2. map every CDM relation to its root (most generic) super-property and fold inverse pairs into one direction;
  3. collapse duplicates created by materialised inference (specific + generic property, both directions).

Usage: python scripts/rdf_analysis/edge_overlap.py [--json tmp/analysis/edges.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdm_ontology import CDM, load_cdm, short  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RES = "http://publications.europa.eu/resource/"
CELLAR_RE = re.compile(r"/cellar/([0-9a-f-]{36})(?:\.\d+)*")


CELEX_SECTORS = {
    "0": "consolidated text", "1": "treaty", "2": "international agreement", "3": "legislation",
    "4": "complementary legislation", "5": "preparatory act", "6": "case-law", "7": "national implementing measure",
    "8": "national case-law", "9": "parliamentary question", "C": "OJ C", "E": "EFTA",
}


def node_kind(key: str) -> str:
    """Coarse document kind of a canonical node key (CELEX sector, otherwise the identifier scheme)."""
    if key.startswith("celex:"):
        return "celex-" + CELEX_SECTORS.get(key[6], "other")
    return key.split(":", 1)[0].split("/", 1)[0]


def canonical_key(group: set[str]) -> str:
    celex = sorted(u for u in group if "/celex/" in u)
    if celex:
        return "celex:" + celex[0].rsplit("/", 1)[-1]
    cellar = sorted(u for u in group if "/cellar/" in u)
    if cellar:
        return "cellar:" + cellar[0].rsplit("/", 1)[-1]
    return sorted(group)[0].replace(RES, "")


def alias_map(g: Graph) -> dict[str, str]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for s, o in g.subject_objects(OWL.sameAs):
        parent[find(str(s))] = find(str(o))
    groups: dict[str, set[str]] = defaultdict(set)
    for node in list(parent):
        groups[find(node)].add(node)
    mapping = {}
    for members in groups.values():
        key = canonical_key(members)
        for m in members:
            mapping[m] = key
    return mapping


def root_of(cdm, uri: str) -> str:
    """Most generic cdm: ancestor (property itself when it has none)."""
    anc = {a for a in cdm.ancestors(uri) if a in cdm.properties}
    roots = [a for a in anc if not any(s in cdm.properties for s in cdm.properties[a].super_props)]
    return sorted(roots)[0] if roots else uri


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=ROOT / "tmp" / "analysis" / "edges.json")
    args = ap.parse_args()
    cdm = load_cdm()

    # fold inverse pairs: inverse relationships are only declared on specific properties, so lift them to the roots
    root_inverse: dict[str, set[str]] = defaultdict(set)
    for uri, info in cdm.properties.items():
        for inv in info.inverse:
            if inv in cdm.properties:
                root_inverse[root_of(cdm, uri)].add(root_of(cdm, inv))
    fwd: dict[str, tuple[str, bool]] = {}

    def direction(p: str) -> tuple[str, bool]:
        """(canonical root property, inverted?) - the lexicographically smaller root of an inverse pair is forward."""
        if p not in fwd:
            r = root_of(cdm, p)
            inv_roots = root_inverse.get(r, set()) - {r}
            fwd[p] = (min(inv_roots), True) if inv_roots and min(inv_roots) < r else (r, False)
        return fwd[p]

    all_edges: dict[tuple, set[str]] = defaultdict(set)
    per_file = {}
    for path in sorted((ROOT / "tmp").glob("*.rdf")):
        g = Graph()
        g.parse(path, format="xml")
        amap = alias_map(g)
        raw = Counter()
        file_edges: set[tuple] = set()
        for s, p, o in g:
            ps = str(p)
            if not ps.startswith(CDM) or isinstance(s, BNode) or isinstance(o, (BNode, Literal)):
                continue
            info = cdm.properties.get(ps)
            if info is None or info.kind != "object":
                continue
            raw[ps] += 1
            rel, inverted = direction(ps)
            a, b = amap.get(str(s), str(s).replace(RES, "")), amap.get(str(o), str(o).replace(RES, ""))
            if inverted:
                a, b = b, a
            file_edges.add((short(rel), a, b))
        for e in file_edges:
            all_edges[e].add(path.stem)
        per_file[path.stem] = {"raw_object_triples": sum(raw.values()), "unique_edges": len(file_edges)}
        print(f"{path.stem:48s} raw={sum(raw.values()):7d} unique_edges={len(file_edges):7d}", flush=True)

    types = Counter(e[0] for e in all_edges)
    multi = Counter(e[0] for e, files in all_edges.items() if len(files) > 1)
    nodes = {e[1] for e in all_edges} | {e[2] for e in all_edges}
    node_kinds = Counter(node_kind(n) for n in nodes)
    citing_kinds = Counter(node_kind(e[2]) for e in all_edges if e[0] == "cdm:cited_by")
    summary = {
        "per_file": per_file,
        "raw_total": sum(v["raw_object_triples"] for v in per_file.values()),
        "sum_unique_per_file": sum(v["unique_edges"] for v in per_file.values()),
        "unique_edges_overall": len(all_edges),
        "edges_in_more_than_one_file": sum(1 for f in all_edges.values() if len(f) > 1),
        "distinct_nodes": len(nodes),
        "node_kinds": node_kinds.most_common(),
        "citing_node_kinds_of_cited_by_edges": citing_kinds.most_common(),
        "roots_with_several_inverse_roots": {short(k): sorted(short(x) for x in v) for k, v in root_inverse.items() if len(v - {k}) > 1},
        "edge_types": types.most_common(),
        "edge_types_shared_between_files": multi.most_common(),
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print({k: v for k, v in summary.items() if k not in ("per_file", "edge_types", "edge_types_shared_between_files")})
    for name, n in types.most_common(40):
        print(f"{n:7d} {name}")


if __name__ == "__main__":
    main()
