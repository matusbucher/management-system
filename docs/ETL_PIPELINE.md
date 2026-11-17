# ETL pipeline – usage, configuration and statistics

Implementation of the strategy in [ETL_TRANSFORMER_LOADER_STRATEGY.md](ETL_TRANSFORMER_LOADER_STRATEGY.md); code in [src/etlpipe/](../src/etlpipe),
runner [src/etl_cli.py](../src/etl_cli.py), tests in [test/test_etl_pipeline.py](../test/test_etl_pipeline.py). The whole database population
(configuration, ontology, loading a list of works, statistics) is a script around this pipeline: [DATABASE_POPULATION.md](DATABASE_POPULATION.md).

```
Extractor ──Graph──▶ TransformerChain (9 steps, Graph→Graph) ──canonical graph──▶ Neo4jLoader (GraphProjector → UNWIND/MERGE)
   │                        │                                                         │
   └──────── ExtractReport  └── StepReport per step ──── graph summary ─────────────  └── LoadReport      => PipelineReport (JSON, log)
```

## 1. Running it

```powershell
python src\etl_cli.py data\analysis\documents                  # all *.rdf of the directory: transform + project, NO database (default)
python src\etl_cli.py data\analysis\documents\NIS2.rdf --log-level DEBUG       # one file, full breakdowns in the log
python src\etl_cli.py data\analysis\documents --load --password <pw>           # write to Neo4j (constraint + indexes are created automatically)
python src\etl_cli.py --work-id 0caf473a-85bd-11ed-9887-01aa75ed71a1 --load      # fetch from Cellar instead of a file
python src\etl_cli.py --work-ids-file data\work_ids.txt --lifecycle --load       # fetch the works listed by scripts\data_acquisition\gather_work_ids.py (see ACQUISITION_STRATEGY.md)
python src\etl_cli.py data\analysis\documents --lifecycle                      # also track the document lifecycle: dossiers (procedures) and their events
python -m unittest test.test_etl_pipeline -v                # 31 tests, no database needed
```

Useful options: `--report-dir` (default `tmp/etl_reports`), `--snapshot-dir DIR` (Turtle after every step), `--log-file`, `--top N` (shorten breakdowns),
`--categories`, `--wemi-levels`, `--canonical-scheme celex|cellar`, `--citation-sources legislation,consolidated`, `--lifecycle`, `--reconcile-aliases` (needs APOC).

From code:

```python
pipeline = EtlPipeline(FileExtractor(), TransformerChain.default_chain(), Neo4jLoader(db), TransformOptions(), report_dir=Path("tmp/etl_reports"))
reports = pipeline.run_many(files)            # one PipelineReport per document; a failing document is reported, the batch continues
pipeline.write_aggregate(reports)             # per-step statistics summed over documents
```

## 2. Interfaces (src/etlpipe/interfaces.py)

| Interface | Method | Notes |
|---|---|---|
| `ExtractorInterface` | `extract(source) -> Graph` | `CellarExtractor` (API), `FileExtractor` (local RDF/XML) |
| `TransformerInterface` | `name`, `transform(graph, ctx: TransformContext) -> Graph` | may modify and return the same graph; writes statistics to `ctx.stats` |
| `LoaderInterface` | `load(graph, ctx: LoadContext) -> LoadReport` | `Neo4jLoader`; `ctx.dry_run` projects without writing |

`TransformerChain` is itself a transformer (chains nest). Steps are independent classes in [src/etlpipe/steps/](../src/etlpipe/steps); a custom chain is just a list:
`TransformerChain([AliasResolver(), WemiLevelFilter(), ...])`.

## 3. The chain

| # | Step | What it does | Main counters (in the report) |
|---|---|---|---|
| 1 | `alias_resolver` | `owl:sameAs` groups → one canonical URI (CELEX, else Cellar UUID); identifiers (`kms:celex`, `cellarId`, `eli`, `ojId`) and `kms:alias` on the canonical node | `alias_groups`, `uris_merged`, `triples_rewritten`, `sameas_removed`; breakdowns `canonical_by_scheme`, `alias_group_size`, `identifiers_added`, `identifier_conflicts` |
| 2 | `wemi_filter` | removes expression/manifestation/item nodes (per `options.wemi_levels`) and, unless the `context` category is on, non-work entities (dossiers, procedures, events) | `nodes_removed`, `triples_removed`, `axioms_removed`; `node_levels`, `level_evidence`, `nodes_removed_by_level` |
| 3 | `predicate_filter` | drops triples the policy tables do not keep | `kept`, `dropped`; `dropped_by_reason` (`category_disabled`, `excluded_relation`, `excluded_attribute`, `unmapped_relation`, `system_metadata`, …) and one breakdown per reason with the predicates |
| 4 | `relation_canonicalizer` | folds generic/specific twins, one direction per relation (`amended_by` → `AMENDS` reversed), rewrites annotations with their relation | `relation_triples_in`, `duplicates_folded`, `edges_out`, `triples_inverted`, `axioms_in/rewritten`, `axioms_headless_removed`, `axioms_dropped_with_relation`; `edges_by_type` |
| 5 | `attribute_mapper` | `cdm:*` literals → `kms:<name>`, drops placeholders (`9999-12-31`, `1001-01-01`) | `attribute_triples_in/out`; `attributes_by_name`, `dropped_attributes`, `sentinel_values_dropped` |
| 6 | `annotation_cleaner` | keeps useful `annot:*`, cleans `{CODE\|URI}`, computes the edge *locator*, merges equal annotations | `axioms_in/out`, `axioms_empty_removed`; `annotations_kept`, `annotations_dropped`, `annotated_edges_by_type` |
| 7 | `type_reducer` | one `kms:docType` (deepest non-technical CDM class, else derived from the CELEX letter), node kinds, `kms:stub` | `type_triples_removed`, `doc_type_from_celex`; `node_kinds`, `doc_types` |
| 8 | `lifecycle_enricher` | dossier/event attributes from their URIs (`procedureId`, `eventDate`, `eventCode`, `byBody`); derives missing `EVENT_OF` edges | `event_of_derived`, `dossiers_created_from_events`; `attributes_added`, `events_without_date` |
| 9 | `scope_filter` | tags `kms:sourceKind` (CELEX sector) and optionally restricts the sources of `CITES` | `citations_dropped`; `source_kinds`, `citations_dropped_by_source_kind` |

After the chain `summarize_graph` adds the final numbers (nodes by kind, document types, edges by type, annotated edges, annotation properties) to the report.

## 4. Configuration (data, not code) – [src/etlpipe/config/](../src/etlpipe/config)

| File | Content | Edit when |
|---|---|---|
| `relations.csv` | CDM relation → canonical type, direction, category (`legal`, `classification`, `agent`, `context`, `actor`, `language`). Looked up along the property's super-property chain, so a specific row overrides a generic one | a relation is missing (`unmapped_relation` in the report) or should be named/directed differently |
| `attributes.csv` | literal property → `kms:` name (blank = drop) | a work attribute should be kept |
| `annotations.csv` | `annot:*` → `kms:` name, `identity` = part of the edge locator | an edge annotation should be kept/dropped |
| `doc_types.csv` | technical CDM classes that never become `docType` | – |
| `cdm_model.json` | generated: property ancestor chains, WEMI levels, class depths | after a new CDM version: `python scripts\rdf_analysis\build_cdm_model.py` |

Defaults of the open decisions from the strategy: canonical key = **CELEX URI**; parallel annotated edges (identity `(start, type, end, locator)`); citations are **tagged, not
filtered** (`--citation-sources` restricts them); lifecycle entities (dossiers and events) **off** (`--lifecycle`, see §5); other non-work CDM entities (`--categories …,context`) **off**; titles are not
available (expression level).

## 5. Document lifecycle (`--lifecycle`)

The EU legislative procedure is modelled as **dossier → events**: a *dossier* (`procedure/2020_359`) is the whole procedure; its *events*
(`procedure-event/2020_359.2022-12-27_PUB_OJ`) are the steps (proposal adopted, Council deliberation, EP opinion, publication in the OJ …);
documents are tied to both. Enabled with `--lifecycle` (relation category `lifecycle`); off by default.

```
(:Dossier)-[:INITIATED_BY]->(:Work proposal)         (:Work act)-[:PRODUCED_BY]->(:Dossier)
(:Work)-[:IN_PROCEDURE]->(:Dossier)                 all documents of the procedure
(:Work)-[:AT_EVENT]->(:Event {eventDate, eventCode, byBody, procedureId})-[:EVENT_OF]->(:Dossier {procedureId})
(:Event)-[:HAS_TYPE]->(:Concept)                     (:Dossier)-[:SUCCEEDS]->(:Dossier)   (:Dossier)-[:BASED_ON]->(:Work|:Concept)
```

Lifecycle of one document: `MATCH (w:Work {celex:'32022L2555'})-[:PRODUCED_BY]->(d)<-[:EVENT_OF]-(e) RETURN e.eventDate, e.eventCode, e.byBody ORDER BY e.eventDate`.

How the pipeline handles it:

* Events are recognised by URI scheme (`procedure-event`, `internal_proc-event`, `intproc-event`, `case-event`, `session-sitting`, `pegase/….date_…`), dossiers by
  `procedure`, `internal_proc`, `intproc`, `case`, `session`. Every event also has a Cellar alias `cellar/<uuid>.NNNN` that **looks like an Expression**; the alias resolver
  keeps the readable URI as canonical, so events are not discarded by the WEMI filter (they used to be).
* The dumps carry **no literals** on dossiers and events; `lifecycle_enricher` reads date, code, issuing body and procedure id from the URI
  (`…_ADP_PROPLEG_byCOM` → `eventCode ADP_PROPLEG`, `byBody COM`; `case-event/C-245%2F25.CC_NC_PUB_OJ_2026-01-26` → `caseId C-245/25`, `eventDate 2026-01-26`).
* Only ≈ 70 events per 3,000 are linked to their dossier explicitly in the data; `EVENT_OF` is derived from the URI for the rest (`dossiers_created_from_events` counts
  dossiers that exist only because of that).
* Generic `PART_OF` membership is split into `IN_PROCEDURE` / `AT_EVENT` / `EVENT_OF` so the three kinds of link can be told apart (`config/relations.csv`, rule lookup takes the most specific entry).
  OJ-collection membership stays excluded.
* Loader: `:Dossier` / `:Event` nodes (plus a label from `docType`, e.g. `:ProcedureInterinstitutional`, `:EventLegal`); indexes on `Event.eventDate` and `Dossier.procedureId`.

Result on the 14 sample documents (`python src\etl_cli.py data\analysis\documents --lifecycle`, summed over documents before cross-document merging):

| | |
|---|---:|
| `:Event` nodes (all with `eventDate`) | 3,162 |
| `:Dossier` nodes | 1,721 |
| `AT_EVENT` / `IN_PROCEDURE` / `EVENT_OF` | 3,673 / 3,010 / 2,871 (68 explicit, 2,803 derived) |
| `PRODUCED_BY` / `INITIATED_BY` / `SUCCEEDS` / `HAS_TYPE` | 624 / 224 / 337 / 42 |

## 6. Statistics and logging

* **Logging** – logger `etlpipe.*`: `etlpipe.pipeline` (extract, canonical graph), `etlpipe.transform` (one INFO line per step: triples in → out, delta, time, headline counters;
  DEBUG: every counter and breakdown; WARNING: step warnings), `etlpipe.load`. `configure_logging(level, log_file)` sets it up (the CLI does it).
* **Per document** – `<report-dir>/<name>.json` (`PipelineReport`: extract, every step with counters/breakdowns/warnings/duration, canonical-graph summary, load report, error) and one
  compact line in `runs.jsonl`. `report.summary_text()` prints the table shown by the CLI.
* **Over documents** – `aggregate.json` (`aggregate_reports`): per step, triples in/out/time and all counters and breakdowns summed; nodes/edges by type; load counters.
* `TransformerChain(..., snapshot_dir=...)` stores the graph after each step so any number can be traced to the triples behind it.

### Result on the 14 sample documents (`python src\etl_cli.py data\analysis\documents`)

| | |
|---|---:|
| triples extracted | 1,030,506 |
| triples in the canonical graph (sum over files) | 1,035,134 (incl. added identifiers/types) |
| alias groups with two or more CELEX numbers / ELI / OJ ids (only one is kept as identifier, all stay in `alias`) | 393 / 69 / 23 |
| relation triples → unique edges after folding | 419,969 → 210,112 (per file, summed) |
| annotation axioms kept after cleaning | 49,895 (of 53,112; 2,029 headless and 462 of dropped relations removed) |
| nodes after loading all 14 documents (`MERGE` union) | 24,594: 9,798 works, 12,606 work stubs, 2,052 concepts, 138 institutions |
| relationships after loading all 14 documents | 154,316 (131,586 distinct start/type/end); 35 % of the rows are saved by `MERGE` |
| top relation types | `CITES` 100,551 · `IS_ABOUT` 18,079 · `AMENDS` 8,274 · `CREATED_BY` 7,672 · `BASED_ON` 6,892 · `IMPLEMENTS` 6,156 |
| run time | ≈ 2–2.5 min (GDPR alone ≈ 70 s, mostly parsing) |

## 6. Known limits

* The Neo4j writer is tested against a fake database (statement shape, ordering, batching, idempotent identity keys); no live Neo4j was available while implementing. Run `--load` on an empty
  database first and compare node/relationship counts with the table above.
* `--reconcile-aliases` (merging works first stored under different identifiers; 1 pair in the sample) uses APOC and is untested.
* Re-loading never deletes: an edge that disappeared from a newer dump stays in the database.
* Dossier/event nodes exist only for lifecycle tracking (`--lifecycle`); the dumps give them no title or label, so everything known about them is derived from their URIs (§5).
* `session-sitting` events are not linked to a session dossier automatically (their URI does not state it reliably).
* Work titles are absent from the dumps (expression level); `title` is kept only where Cellar provides it on the work.
