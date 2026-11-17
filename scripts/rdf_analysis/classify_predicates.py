"""Aggregate the per-file profiles and classify every RDF term for the work-level transformer.

Inputs : data/analysis/profile/*.json (profile_rdf.py), docs/cdm ontology.
Outputs: docs/rdf_analysis/predicate_classification.csv
         docs/rdf_analysis/type_classification.csv
         docs/rdf_analysis/summary.json   (numbers quoted in docs/RDF_METADATA_ANALYSIS.md)

Usage: python scripts/rdf_analysis/classify_predicates.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdm_ontology import ANNOTATION, CDM, CDM_CMR, PropertyInfo, load_cdm, short  # noqa: E402
from edge_overlap import root_of  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "data" / "analysis" / "profile"
OUT = ROOT / "docs" / "rdf_analysis"

OWL = "http://www.w3.org/2002/07/owl#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SKOS = "http://www.w3.org/2004/02/skos/core#"

# ---- decisions that cannot be derived from the ontology ------------------------------------------------------------
# Edge annotations (owl:Axiom payload) that describe the *relation between two works* and therefore stay.
ANNOT_KEEP = {
    "article": "location inside the target act (legal basis / citation)",
    "paragraph": "location inside the target act (legal basis / citation)",
    "subparagraph": "location inside the target act (legal basis / citation)",
    "comment_on_legal_basis": "qualifier of a legal-basis relation (e.g. P1, P3)",
    "eli_target": "ELI of the cited article/paragraph of the target act",
    "fragment_citing_source": "fragment of the citing act that contains the citation (case-law citations)",
    "fragment_cited_target": "fragment of the cited act that is referred to",
    "reference_to_modified_location": "location in the amended act (amendment granularity, e.g. ART:8 PAR:1)",
    "reference_to_modifying_location": "location in the amending act",
    "start_of_validity": "date from which an amendment/repeal/adoption is valid",
    "end_of_validity": "date until which a relation is valid",
    "type_of_link_target": "kind of link (MS, RD, EA ...) - qualifier of the relation",
    "role2": "role of the target act in an amendment (J, R, DEL, MD ...) - qualifier of the relation",
    "impact": "text vs structure impact of a modification",
    "type_instruction": "explicit / implicit modification instruction",
    "transposition_deadline_transmitted": "transposition deadline for a national implementing measure",
    "transposition_notification": "date a Member State notified a national implementing measure",
    "date": "date linked to the relation (e.g. date of referral)",
    "type_of_date": "qualifier of a date",
    "comment_on_date": "qualifier of a date",
    "result_decision": "outcome of a judicial procedure",
}
ANNOT_DROP = {
    "language_list": "languages concerned by the link - expression-level availability, not work semantics",
    "build_info": "ingestion provenance of the Cellar build tool",
    "production_sequence": "consolidation production sequence number (technical)",
    "error_message": "data-quality note",
    "quality_issue": "data-quality note",
    "order": "list ordering helper",
    "changed_to_identifier": "identifier repair note",
}

# Work-to-work legal relation roots (canonical, class-neutral names) - tier A of the knowledge graph.
TIER_A = {
    "cited_by", "cites", "amended_by", "amends", "repealed_by", "repeals", "implicitly_repealed_by", "implicitly_repeals",
    "adopted_by", "adopts", "basis_for", "based_on", "consolidated_by", "consolidates", "implemented_by", "implements",
    "corrected_by", "corrects", "completed_by", "completes", "replaced_by", "replaces", "derogated_by", "derogates",
    "amendment_proposed_by", "has_successor", "is_logical_successor_of", "influenced_by", "influences", "related_to",
    "is_another_publication_of", "interpreted_by", "interprets", "does_deletion_of", "deleted_by", "codified_version",
    "is_about", "subject_of",
}
# Links of a work to context entities (agents, EuroVoc, dossiers, events, publication) - tier B.
TIER_B_HINT = re.compile(
    r"created_by|creates|responsible|responsibility|published|publishes|part_of|contains|belongs|produced_by|produces|"
    r"initiated|initiates|summariz|reference|edited_by|ep_opinion|eesc_opinion|cor_opinion|opinion_contained"
)


def load_profiles() -> list[dict]:
    """
    Load the per-file profiles written by ``profile_rdf.py``.

    Returns:
        list[dict]: The profiles, ordered by file name.
    """
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PROFILES.glob("*.json"))]


def obj_class(
    kind: str
) -> str:
    """
    Map an object kind from the profiles to a coarse object class.

    Args:
        kind (str): The object kind (e.g. ``literal:string``, ``bnode``, ``uri:eurovoc``).

    Returns:
        str: One of literal, bnode, vocabulary, expression, work, or the unchanged kind.
    """
    if kind.startswith("literal"):
        return "literal"
    if kind == "bnode":
        return "bnode"
    if kind.startswith("uri:authority") or kind == "uri:eurovoc":
        return "vocabulary"
    if kind.endswith(":expression") or kind.endswith(":manifestation"):
        return "expression"
    if kind.startswith("uri:"):
        return "work"
    return kind


def main() -> None:
    """Aggregate the profiles and write the predicate/type classification CSVs and the summary JSON."""
    cdm = load_cdm()
    profiles = load_profiles()
    OUT.mkdir(parents=True, exist_ok=True)

    usage: dict[str, Counter] = defaultdict(Counter)
    subj_levels: dict[str, Counter] = defaultdict(Counter)
    obj_classes: dict[str, Counter] = defaultdict(Counter)
    files: dict[str, set] = defaultdict(set)
    for prof in profiles:
        for lvl, pred, okind, n in prof["pred_usage"]:
            usage[pred]["triples"] += n
            subj_levels[pred][lvl] += n
            obj_classes[pred][obj_class(okind)] += n
            files[pred].add(prof["file"])

    dup_by_super: Counter = Counter()
    for prof in profiles:
        for _p, sup, n in prof["super_property_duplicates"]:
            dup_by_super[sup] += n

    rows = []
    for pred, cnt in sorted(usage.items(), key=lambda kv: -kv[1]["triples"]):
        info = cdm.properties.get(pred)
        total = cnt["triples"]
        dom_subj = subj_levels[pred].most_common(1)[0][0]
        dom_obj = obj_classes[pred].most_common(1)[0][0]
        redundancy = round(dup_by_super[pred] / total, 3) if pred in dup_by_super else 0.0
        root = root_of(cdm, pred) if info else pred
        chain = " > ".join(short(a) for a in sorted(cdm.ancestors(pred) & set(cdm.properties))) if info else ""
        local = pred.rsplit("#", 1)[-1]
        category, action, why = classify(pred, local, info, dom_subj, dom_obj, redundancy, root)
        rows.append({
            "predicate": short(pred),
            "namespace": "cdm" if pred.startswith(CDM) else "cmr" if pred.startswith(CDM_CMR)
            else "annotation" if pred.startswith(ANNOTATION) else "owl/rdf/skos",
            "cdm_kind": info.kind if info else "",
            "cdm_wemi_level": info.level if info else "",
            "level_source": info.level_source if info else "",
            "legal_flag": (info.legal_flag or "") if info else "",
            "label": info.label if info else "",
            "root_property": short(root) if info else "",
            "super_properties": chain,
            "triples": total,
            "files": len(files[pred]),
            "subject_levels": json.dumps(dict(subj_levels[pred].most_common(3))),
            "object_classes": json.dumps(dict(obj_classes[pred].most_common(3))),
            "redundant_with_specific": redundancy,
            "category": category,
            "action": action,
            "rationale": why,
        })

    cols = list(rows[0].keys())
    with (OUT / "predicate_classification.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    # ---- rdf:type classes -------------------------------------------------------------------------------------------
    type_counts: Counter = Counter()
    type_subj: dict[str, Counter] = defaultdict(Counter)
    for prof in profiles:
        for lvl, cls, n in prof["type_usage"]:
            type_counts[cls] += n
            type_subj[cls][lvl] += n
    type_rows = []
    for cls, n in type_counts.most_common():
        levels = sorted(cdm.class_levels(cls)) if cls.startswith(CDM) else []
        category, action, why = classify_type(cls, levels)
        type_rows.append({
            "class": short(cls), "wemi_levels": "+".join(levels), "triples": n,
            "subject_levels": json.dumps(dict(type_subj[cls].most_common(3))),
            "category": category, "action": action, "rationale": why,
        })
    with (OUT / "type_classification.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(type_rows[0].keys()))
        w.writeheader()
        w.writerows(type_rows)

    write_summary(profiles, rows, type_rows)
    print(f"{len(rows)} predicates, {len(type_rows)} classes written to {OUT}")


def classify(
    pred: str,
    local: str,
    info: Optional[PropertyInfo],
    dom_subj: str,
    dom_obj: str,
    redundancy: float,
    root: str
) -> tuple[str, str, str]:
    """
    Classify a predicate for the work-level transformer.

    Args:
        pred (str): The URI of the predicate.
        local (str): The local name of the predicate.
        info (Optional[PropertyInfo]): The CDM property, None when it is not declared in the ontology.
        dom_subj (str): The dominant subject level of the predicate.
        dom_obj (str): The dominant object class of the predicate.
        redundancy (float): Share of the triples duplicated by a more specific sub-property.
        root (str): The URI of the root (most generic) property.

    Returns:
        tuple[str, str, str]: The category, the action and the rationale.
    """
    if pred == RDF_TYPE:
        return "structural", "KEEP-FILTERED", "keep the most specific work class (regulation, directive...); drop technical classes"
    if pred == OWL + "sameAs":
        return "identity", "KEEP-FOLD", "alias URIs (CELEX/ELI/OJ/Cellar) of one work -> identifiers of a single node; drop expression aliases"
    if pred in (OWL + "annotatedSource", OWL + "annotatedProperty", OWL + "annotatedTarget"):
        return "reification", "KEEP-FOLD", "owl:Axiom node is flattened into properties of the annotated relationship"
    if pred.startswith(SKOS):
        return "vocabulary", "OPTIONAL", "concept scheme membership, only needed when vocabularies are loaded as nodes"
    if pred.startswith(CDM_CMR):
        return "system", "OPTIONAL", "Cellar creation/modification timestamps - provenance only"
    if pred.startswith(ANNOTATION):
        if local in ANNOT_KEEP:
            return "edge-annotation", "KEEP-EDGE-PROPERTY", ANNOT_KEEP[local]
        return "edge-annotation", "DROP", ANNOT_DROP.get(local, "technical annotation")
    if info is None:
        return "unknown", "REVIEW", "term not declared in the CDM ontology files"

    if info.level in ("expression", "manifestation", "item"):
        return f"{info.level}-level", "DROP", f"declared for CDM {info.level} level"
    if dom_obj == "expression":
        return "wemi-link", "DROP", "link from work to its expression (hierarchy plumbing, languages)"

    generic = info.level == "generic"
    root_local = root.rsplit("#", 1)[-1]
    if dom_obj == "literal":
        if info.level_source == "name-prefix" and info.level not in ("work",):
            return f"{info.level}-level", "DROP", "name prefix indicates another WEMI level"
        role = "work-attribute"
        return (role + "-generic", "FOLD", "generic duplicate of a work-level attribute") if redundancy >= 0.5 else (role, "KEEP", "literal property of the work")
    # object properties
    if redundancy >= 0.5 and generic:
        return "work-relation-generic", "FOLD", "generic super-property materialised next to its specific sub-property (same value)"
    tier_a = root_local in TIER_A or local in TIER_A
    if dom_subj == "vocabulary" or dom_obj == "vocabulary":
        if "eurovoc" in local or "subject" in local or "is_about" in local or "directory-code" in local or "resource-type" in local:
            return "work-classification", "KEEP", "work <-> EuroVoc / subject-matter / directory-code / resource type"
        if "treaty" in local:
            return "work-classification", "KEEP", "legal basis in a Treaty (concept)"
        if re.search(r"created_by|creates|responsible|responsibility|adopted|authored", local):
            return "work-agent", "KEEP", "institution that created / is responsible for the work"
        return "work-context-entity", "OPTIONAL", "link to agents/courts/persons (mostly case-law actors)"
    if dom_subj == "untyped":
        return "context-entity-link", "OPTIONAL", "dossier / event / procedure membership (non-work CDM class)"
    if tier_a or (info.legal_flag == "true"):
        return "work-relation", "KEEP", "legal relation between two works (CDM flag: relevant for legal analysis)" if info.legal_flag == "true" else "legal relation between two works"
    if TIER_B_HINT.search(local):
        return "work-context-relation", "OPTIONAL", "publication / dossier / opinion context of the work"
    return "work-relation-other", "OPTIONAL", "work-level relation of secondary legal value"


def classify_type(
    cls: str,
    levels: list[str]
) -> tuple[str, str, str]:
    """
    Classify an ``rdf:type`` class for the work-level transformer.

    Args:
        cls (str): The URI of the class.
        levels (list[str]): The WEMI levels of the class.

    Returns:
        tuple[str, str, str]: The category, the action and the rationale.
    """
    local = cls.rsplit("#", 1)[-1]
    if cls == OWL + "Axiom":
        return "reification", "KEEP-FOLD", "container of edge annotations; flattened"
    if cls.startswith(SKOS):
        return "vocabulary", "OPTIONAL", "SKOS concept / scheme"
    if local in ("work", "resource_legal", "evolutive_work", "serial_work", "complex_work", "act_preparatory", "legislation_secondary"):
        return "technical-class", "DROP", "super-class that carries no document-type information"
    if "work" in levels:
        return "work-class", "KEEP", "document type of the work (use most specific class as docType)"
    if local in ("concept", "concept_eurovoc", "resource-type", "subject-matter", "concept_directory-code", "concept_treaty", "concept_decoding"):
        return "vocabulary", "OPTIONAL", "reference-data concept"
    return "other-entity", "OPTIONAL", "non-WEMI entity (agent, event, dossier, period...)"


def write_summary(
    profiles: list[dict],
    rows: list[dict],
    type_rows: list[dict]
) -> None:
    """
    Write the summary numbers (quoted in docs/RDF_METADATA_ANALYSIS.md) to ``summary.json``.

    Args:
        profiles (list[dict]): The per-file profiles.
        rows (list[dict]): The predicate classification rows.
        type_rows (list[dict]): The type classification rows.
    """
    by_action = Counter()
    by_category = Counter()
    for r in rows:
        by_action[r["action"]] += r["triples"]
        by_category[r["category"]] += r["triples"]
    summary = {
        "files": len(profiles),
        "triples_total": sum(p["triples"] for p in profiles),
        "distinct_predicates": len(rows),
        "triples_by_action": by_action.most_common(),
        "triples_by_category": by_category.most_common(),
        "predicates_by_category": Counter(r["category"] for r in rows).most_common(),
        "per_file": [{k: p[k] for k in ("file", "size_bytes", "triples", "subjects_uri", "subjects_bnode", "distinct_predicates", "sameas_groups")} for p in profiles],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
