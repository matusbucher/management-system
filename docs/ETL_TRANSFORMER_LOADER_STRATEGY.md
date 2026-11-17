# Strategy for the ETL transformer and loader

> **Status: implemented** – see [ETL_PIPELINE.md](ETL_PIPELINE.md) for usage, configuration and the statistics reports. Differences from this proposal:
> the attribute renaming is its own step (`attribute_mapper`, step 4b below); `wemi_filter` also removes non-work entities (dossiers, procedures, events) unless the
> `context` category is enabled; the loader writes plain Cypher through `Neo4jDatabase.run_write`. Defaults taken for the open decisions of §9: CELEX canonical key, parallel
> annotated edges, citations tagged by source kind but not filtered, context entities off, relation names in active voice (`config/relations.csv`).

Originally written as a proposal. It builds on [RDF_METADATA_ANALYSIS.md](RDF_METADATA_ANALYSIS.md) (what is in the data) and
[RDF_TRIPLES_GUIDE.md](RDF_TRIPLES_GUIDE.md) (how it looks), and on the current skeleton in [src/etlpipe/](../src/etlpipe):
`CellarExtractor` → `Transformer` (identity stub) → `Loader` (empty), plus `Neo4jDatabase.import_RDF_data` which calls
`n10s.rdf.import.inline(..., "RDF/XML")`.

## 1. Short answer

| Question | Recommendation |
|---|---|
| Transformer | Do the work in **RDF → RDF steps** with rdflib, chained, each step a small pure unit. The chain ends in a *canonical work graph* (clean RDF, one node per work, no aliases, no generic duplicates, no expression noise). |
| Let neosemantics (n10s) load the result? | **Not for the facts.** After cleaning, 8–13 % of the semantics (relationship annotations) and the identity/merge rules still cannot be expressed through n10s configuration (§3). |
| Own loader? | **Yes – a thin one**: project the canonical graph to nodes/relationships in Python and write with `UNWIND … MERGE` through the existing driver wrapper. About 142 k edges / 27 k nodes for all 14 files, so performance is a non-issue. |
| Fix after loading with Cypher? | No. It means loading ~50 k `owl:Axiom` nodes and 400 k noise triples first, then deleting them with dynamic-relationship-type Cypher (APOC). Same effort as an own loader, less control, not atomic. |
| Where n10s is still useful | **Ontologies and vocabularies** (task 5 in [plan.txt](../plan.txt)): CDM OWL, EuroVoc and authority tables as SKOS, via `n10s.onto.import` / `n10s.skos.import`. Share the `uri` key so facts link to them (§5). |

So: *adjust the RDF graph first (yes), then load with our own loader (yes), and use n10s only for the semantic web layer (ontologies/SKOS).*

## 2. What the data demands from the pipeline

From the analysis, a correct load has to do all of the following. Anything the loader cannot do natively must happen earlier:

1. **Merge aliases** (`cellar/…`, `celex/…`, `oj/…`, `eli/…` of one work; the data of one work is split across them).
2. **Drop other WEMI levels** (expressions, `work_has_expression`, `language_list`) – configurable, because `DEFAULT_WEMI_LEVELS = {WORK}` already exists in
   [src/eurlex/constants.py](../src/eurlex/constants.py) and may later grow.
3. **Fold materialised inference** (23 % of triples: `cited_by` + `work_cited_by_work`) and **one direction per inverse pair**
   (the same fact appears as `A cites B` in one file and `B cited_by A` in another).
4. **Turn `owl:Axiom` reification into relationship properties** (article, paragraph, modified location, validity dates, transposition dates…).
5. **Clean values** (`{R|http://…/fd_375/R}` → `R`, `9999-12-31`, `1001-01-01`, `TO_VALIDATE`, `$BUILD_INFO$`).
6. **Reduce `rdf:type`** to one document type.
7. **Scope** (e.g. 72 % of citation edges come from preparatory acts) – a policy switch, not hard-coded.
8. **Idempotent, repeatable load** of 14+ files into one database: the same work/edge arrives many times (30 % of edges occur in several files).

## 3. Why not "just configure neosemantics"

n10s imports RDF with a generic mapping: URI → `:Resource {uri}` node, `rdf:type` → labels, literal → property, resource-valued triple → relationship,
blank node → node. Its knobs (`n10s.graphconfig.init`: `handleVocabUris` SHORTEN/KEEP/MAP/IGNORE, `handleMultival`, `handleRDFTypes`, `keepLangTag`,
`predicateExclusionList`, `applyNeo4jNaming`, optional `n10s.mapping.*` renames) cover naming and some filtering. Against our list:

| Need | n10s | Verdict |
|---|---|---|
| 1 alias merge | creates one node per URI and a `sameAs` relationship; merging afterwards needs `apoc.refactor.mergeNodes` | must be done before load |
| 2 WEMI filter | `predicateExclusionList` excludes a predicate globally; cannot say "`owl:sameAs` only when the subject is an expression" | before load |
| 3 fold / inverse direction | `MAP` can *rename* a predicate; it cannot drop the duplicate, nor reverse an edge | before load |
| 4 relationship properties | `owl:Axiom` blank nodes become ordinary nodes; no join to the relationship they annotate. Only RDF-star import (Turtle-star/TriG-star) produces relationship properties – version-dependent, and rdflib cannot serialise RDF-star, so we would hand-write it | **blocker** (see 3.1) |
| 5 value cleaning | none | before load |
| 6 type reduction | `handleRDFTypes` chooses *how* types are stored, not *which* | before load |
| 8 idempotence | node `MERGE` on `uri` is fine; relationships are merged per (start, type, end), so two edges of the same type between the same works (e.g. two different articles) collapse into one and one annotation set overwrites the other (verify on your plugin version) | **blocker** |
| naming | default labels/types look like `cdm__work_cited_by_work`; `MAP` fixes it only for plain renames | cosmetic |

Also: `n10s.graphconfig.init` is required before any import (the current `import_RDF_data` fails without it); inline import ships the whole RDF string through
Bolt (fine after filtering, not for the raw 64 MB GDPR file).

Once everything blocking is removed *before* the load, what remains for n10s to do is "create nodes and edges from a trivial RDF graph", which is
about 60 lines of own code – and the own code can additionally write relationship properties, choose the key and control the merge. That is the argument for the own loader.

### 3.1 Options compared

| Option | Description | Pros | Cons |
|---|---|---|---|
| A. Pure n10s | RDF/XML in, default config | zero code | loads the noise; no edge properties, no alias merge; unusable result |
| B. n10s + post-load Cypher | filter little, import, clean up in the DB | quick first import | clean-up needs dynamic rel types (APOC), is slow on 400 k nodes, is not atomic, hard to test |
| **C. RDF transformer chain + own loader** | all rules in tested Python, load by `MERGE` | full control, testable without a DB, deterministic, small | ~300 lines of loader/projector to write |
| D. RDF transformer chain + RDF-star → n10s | emit Turtle-star, let n10s create relationship properties | reuses n10s for the last step | depends on n10s version, hand-written serialiser, parallel-edge problem remains, naming still needs `MAP` |

Spike worth 1–2 hours *later*, not now: check whether your n10s version imports RDF-star and how it treats two same-type edges between the same pair. If both are fine, D becomes a
drop-in replacement of the *writer* only (the transformer chain does not change) – the design below keeps that door open.

## 4. Proposed design

### 4.1 Pipeline

```
Extractor ──Graph──▶ Transformer chain (Graph→Graph, N steps) ──canonical Graph──▶ Loader = Projector ─▶ Writer ─▶ Neo4j
```

`EtlPipeline(extractor, transformers, loader).run(resource_id)` (plus `run_many` for the 14 documents). Each document is processed independently; the
database does cross-document de-duplication through `MERGE`. No global state between files.

### 4.2 Transformer interface

Keep the existing shape (`Graph → Graph`), add a context object and make the chain itself a transformer (composite), so chains can be nested and reused.

```python
@dataclass
class TransformContext:
    focal: CellarResourceId | None          # the work that was requested
    options: TransformOptions               # wemi_levels, citation_scope, include_context_entities, ...
    report: TransformReport                 # per-step counters: triples in/out, dropped by reason, warnings

class TransformerInterface(Protocol):
    name: str
    def transform(self, graph: Graph, ctx: TransformContext) -> Graph: ...

class TransformerChain:                     # also a TransformerInterface
    def __init__(self, steps: Sequence[TransformerInterface], *, snapshot_dir: Path | None = None): ...
    def transform(self, graph, ctx):
        for step in self.steps:
            graph = step.transform(graph, ctx)      # records triple counts; optionally serialises a snapshot per step
        return graph
```

Design rules:

* **Pure by contract, mutating allowed**: a step may modify and return the same `Graph` (copying 500 k triples per step is wasteful); the pipeline owns the graph, steps do not keep references.
* **Every step's output is valid RDF and every prefix of the chain is loadable/inspectable.** Steps communicate *through the graph* (e.g. aliases are rewritten to canonical URIs and the old
  URIs stored as `kms:alias` triples), not through hidden state. This also keeps option D open.
* **Policy in data, not code**: keep/fold/drop decisions and the relation-name/direction table are files (CSV/YAML in `src/etlpipe/config/`), seeded from
  [rdf_analysis/predicate_classification.csv](rdf_analysis/predicate_classification.csv). Steps read them; changing a decision needs no code change.
* **Statements with annotations are rewritten together**: any step that rewrites or removes `(s, p, o)` must also rewrite/remove the `owl:Axiom` that annotates it. Put that in one helper
  (`rewrite_statement`), used only by the alias and relation steps.
* **Report instead of silently dropping**: each step counts what it removed and why (also useful for the thesis evaluation).

### 4.3 Steps (order matters)

| # | Step | Does | Source in analysis |
|---|---|---|---|
| 1 | `AliasResolver` | union-find over `owl:sameAs`; rewrite every occurrence (including axioms) to the canonical URI (CELEX → Cellar UUID → first); store old URIs as `kms:celex`, `kms:cellarId`, `kms:eli`, `kms:oj`, `kms:alias`; drop `sameAs` | §4.2, 6.2 |
| 2 | `WemiLevelFilter(levels)` | classify each node (URI structure → `rdf:type` → predicate domain); drop expression/manifestation/item nodes and `work_has_expression`; keep vocabulary nodes only as targets | §4.1, 5.4 |
| 3 | `PredicateFilter(profile)` | apply KEEP/DROP/OPTIONAL from the policy table; drop `language_list`, `build_info`, case-law actor links and dossier/event context unless the profile enables them | §5.1–5.4 |
| 4 | `RelationCanonicalizer` | fold generic twins into the specific property, map to a canonical relation name, normalise direction (active voice: `amended_by` → `amends`), de-duplicate, rewrite axioms accordingly | §5.5 |
| 5 | `AnnotationCleaner` | keep whitelisted `annot:*` only; parse `{CODE\|URI}` → `CODE`; map sentinels to absent; drop headless axioms; give each remaining axiom a deterministic key | §4.3, 5.3 |
| 6 | `TypeReducer` | keep the most specific work class as `kms:docType`; drop technical classes | §5.2 |
| 7 | `ScopeFilter(options)` | optional policy: restrict e.g. `CITES` sources by CELEX sector (legislation / preparatory / case-law / NIM); tag the rest with `kms:sourceKind` instead of dropping, if desired | §1.7, 6.9 |

Steps 2–3 may be swapped; 4 must come after 3 (needs original property names), 5 after 4 (axioms already canonical). The result uses a small own vocabulary `kms:` for what CDM does not express
(`kms:docType`, `kms:CITES`, `kms:celex`, …), so the output is plain, easy-to-read RDF and a loader needs no CDM knowledge.

### 4.4 Loader interface

Split *what to write* (pure, unit-testable) from *writing it*:

```python
class LoaderInterface(Protocol):
    def load(self, graph: Graph, ctx: LoadContext | None = None) -> LoadReport: ...

# internals
class GraphProjector:        # canonical RDF -> PropertyGraphBatch(nodes: list[NodeRow], rels: list[RelRow])
class Neo4jWriter:           # ensure_schema(); write(batch) with UNWIND ... MERGE in chunks of ~5k per transaction
```

* `ensure_schema()` – idempotent constraints/indexes (§5), run once per pipeline start.
* `write()` – nodes first (`MERGE (w:Resource:Work {uri:$uri}) SET w += $props`), then relationships grouped **by type** (Cypher cannot parametrise
  relationship types; the type set is small and comes from the whitelist, so build one statement per type – no APOC needed).
* Returns `LoadReport` (nodes/relationships created vs. matched, skipped, duration).
* `Neo4jDatabase` stays the connection wrapper (it needs `run_write(query, params)` with explicit transactions/batches; `run_query` returns everything as dicts and is unsuitable for writes).
  `import_RDF_data` is kept only for ontology/SKOS import (§6).

### 4.5 Property-graph model (to be aligned with the schema task)

* Nodes: `(:Resource:Work {uri, celex, cellarId, eli, oj, docType, year, inForce, dateEntryIntoForce, dateEndOfValidity, stub})` – `stub = true` for works known only as a
  target of some relation (the majority of the ~27 k nodes) so the UI can distinguish fetched documents; `(:Resource:Concept {uri, scheme})`, `(:Resource:Institution {uri, code})`.
  Optional secondary label from `docType` (`:Regulation`, `:Directive`) – convenient for queries.
* Relationships between works, active voice from the acting document to its target: `CITES`, `AMENDS`, `REPEALS`, `IMPLICITLY_REPEALS`, `ADOPTS`, `BASED_ON`,
  `IMPLEMENTS`, `CONSOLIDATES`, `CORRECTS`, `COMPLETES`, `REPLACES`, `AMENDMENT_PROPOSED_FOR`, `IS_ANOTHER_PUBLICATION_OF`, `RELATED_TO` (the names in
  [plan.txt](../plan.txt) – `ADOPTS_…`, `REPEALS_…`, `CITES` – fit; type-specific variants can be added by the relation table). Edge properties come from the whitelisted annotations
  (`article`, `paragraph`, `modifiedLocation`, `startOfValidity`, `transpositionDeadline`, …).
* Reference links: `(:Work)-[:IS_ABOUT]->(:Concept)`, `(:Work)-[:CREATED_BY|RESPONSIBLE_FOR]->(:Institution)`.

## 5. Identity and merge rules (the part most likely to go wrong)

* **Single key `uri` on label `:Resource`**, value = canonical URI chosen by `AliasResolver`. This is the same key n10s uses, so ontology/SKOS nodes loaded by n10s and our
  Concept/Institution nodes unify automatically, and one uniqueness constraint covers everything (`CREATE CONSTRAINT … FOR (r:Resource) REQUIRE r.uri IS UNIQUE`).
* **Cross-file alias drift**: a work may be referenced only as `oj/L_2024…` in file 1 and appear with its CELEX alias in file 2 → two nodes. Mitigation: keep alias properties
  (`celex`, `cellarId`, `oj`, `eli`) with indexes, and run a cheap **reconcile step after each load** that merges nodes sharing an identifier (≈27 k nodes: negligible); `apoc.refactor.mergeNodes` or, without APOC, a
  small Python-driven merge. Alternative, if drift turns out to be rare: accept stubs and reconcile only on demand.
* **Edge identity** `(start, type, end, locator)` where `locator` = `article/paragraph` or `modifiedLocation` when present, otherwise empty. This lets the same pair carry several annotated edges
  (e.g. amended at two articles) and makes re-loads idempotent. Decision needed: parallel edges (above) versus one edge with list properties (simpler queries, loses per-article validity).
* **Re-load semantics**: `MERGE` + `SET` replaces properties of existing nodes/edges but never deletes. Stale-data removal (e.g. an edge amended away) is a separate, explicit operation
  (`source` property on edges + "delete edges of source X not seen in this run") – defer until needed.
* **Provenance**: optional `loadedFrom` (focal Cellar ID) and `loadedAt` on nodes/edges; cheap and useful for debugging overlap between files.

## 6. Where n10s stays in the picture

* **Ontologies** (CDM classes/properties, WEMI hierarchy – task 1/5): `n10s.onto.import.fetch` on the files in [data/cdm/](../data/cdm) into the same database; they live as
  `:Class`/`:Relationship`/`:Property` nodes and do not collide with `:Work` data.
* **Vocabularies** (EuroVoc, authority tables with labels – the dumps contain none): `n10s.skos.import` produces `:Resource:skos__Concept` nodes keyed by `uri`; our loader
  `MERGE`s on the same `uri`, so `IS_ABOUT` edges attach to labelled concepts once those are imported.
* Configure the graph once (`n10s.graphconfig.init` with `handleMultival: "ARRAY"`, `keepLangTag: true`, `handleVocabUris: "SHORTEN"`) and keep the setup in a small `schema`/`setup`
  routine together with `ensure_schema()`, so a fresh database is reproducible.
* Facts are written by our loader with plain Cypher property names (`docType`, `CITES`), **not** n10s prefixed names. The two worlds are joined only through `uri`.

## 7. Testing

* **Transformer steps**: unit tests with 20–50-triple Turtle fixtures cut from DORA/NIS2 (one fixture per rule: alias group, expression noise, twin folding, inverse direction,
  annotated edge, headless axiom, placeholder values). No database needed.
* **Chain**: golden-file test on `DORA.rdf` (small, 18 k triples): expected canonical graph counts (nodes, edges per type) stored in the repo; guards regressions when policy tables change.
* **Projector**: canonical RDF → expected node/relationship rows.
* **Loader**: integration test against a throw-away Neo4j (existing [test_database.py](../test/test_database.py) pattern): load DORA twice → identical counts (idempotence); load DORA + NIS2 →
  shared edges counted once.
* **Analysis scripts** stay as the oracle: `edge_overlap.py` already computes unique-edge counts per file – the loader's numbers should match it.

## 8. Phasing

1. **Policy tables** – export keep/fold/drop and the relation-name/direction table from the analysis CSV into `src/etlpipe/config/` (decide the ≈25 inverse pairs by hand).
2. **Chain skeleton** – `TransformContext`, `TransformerChain`, report, snapshots; steps 1–4 (alias, WEMI, filter, canonicalise). Output of DORA ≈ 4 k edges.
3. **Annotations + types** – steps 5–6.
4. **Loader** – schema, projector, writer, idempotence test; load DORA, then all 14 files; compare with `edge_overlap.py`.
5. **Scope filter and options** – citation scope, context entities, WEMI levels via CLI flags.
6. **n10s layer** – ontology and SKOS import; optional spike of RDF-star (§3.1).

## 9. Decisions needed from you

1. **Canonical key**: `uri` = CELEX URI where available (readable, matches EUR-Lex) – acceptable, or prefer the Cellar UUID URI (always present, opaque)?
2. **Edge multiplicity**: parallel annotated edges (recommended) or one edge with list properties?
3. **Citation scope**: keep all `CITES` (87 k edges, 72 % from preparatory acts) or only legislation + consolidated + NIM; or keep with a `sourceKind` tag?
4. **Context entities**: load dossiers/procedures/events (≈ 12.7 k triples) or only works, concepts and institutions?
5. **Titles**: expression-level and absent from the dumps – add a separate extractor step (one expression per work) before the chain is finalised?
6. **Relation naming**: confirm the active-voice convention and whether specific variants (`ADOPTS_REGULATION`…) are wanted over the generic names.
