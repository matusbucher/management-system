# Populating the Neo4j database

How an empty Neo4j database is turned into the knowledge graph: [scripts/data_load/populate_database.py](../scripts/data_load/populate_database.py)
runs the whole process (configuration, CDM ontology, documents, reference data labels, statistics) and logs and reports every step.

```powershell
python scripts\data_load\populate_database.py --limit 3                  # try the whole process on the first 3 works of the list
python scripts\data_load\populate_database.py                            # populate with data/work_ids.txt (491 works, several hours)
python scripts\data_load\populate_database.py --resume data\population\<run>   # continue an interrupted run
python scripts\data_load\populate_database.py --reset --yes              # delete everything in the database first
```

Requirements: Neo4j running (default `localhost:7687`, user `neo4j`, password `password` or `$NEO4J_PASSWORD`/`--password`) with the
**neosemantics (n10s)** plugin. **APOC is optional** (only the merging of duplicated works needs it). The list of works comes from
[ACQUISITION_STRATEGY.md](ACQUISITION_STRATEGY.md). Code: `scripts/data_load/` (`populate_database.py` the runner, `database_setup.py` the
database preparation and statistics, `summary.py` the report, `test_populate.py` the tests); it uses the ETL pipeline of
[ETL_PIPELINE.md](ETL_PIPELINE.md) as a library.

## 1. The phases

Nine phases, each logged (`phase 6/9: documents`), timed, and recorded in the summary with its status (`ok`, `skipped`, `failed`, `interrupted`).
Every phase is **idempotent**: the script can be started on an empty database, on a half-populated one, or twice in a row.

| # | Phase | What happens | Why |
| --- | --- | --- | --- |
| 1 | environment | connects, reads server version, checks n10s and APOC, counts what is already in the database; with `--reset --yes` deletes all nodes | fail early with a clear message; the n10s plugin is mandatory (the ontology import needs it) |
| 2 | schema | `CREATE CONSTRAINT/INDEX ... IF NOT EXISTS`: unique `:Resource(uri)`, indexes on `Work.celex`, `Work.cellarId`, `Event.eventDate`, `Dossier.procedureId` | the loader `MERGE`s on `uri`; without the constraint it would be slow and could duplicate nodes. The statements are the loader's own (`SCHEMA_STATEMENTS`) |
| 3 | n10s | `n10s.graphconfig.init` with `handleVocabUris: SHORTEN`, `handleMultival: ARRAY`, `keepLangTag: true`, `handleRDFTypes: LABELS` unless a configuration exists | n10s refuses to import before it is configured; the values are the ones decided in [ETL_TRANSFORMER_LOADER_STRATEGY.md](ETL_TRANSFORMER_LOADER_STRATEGY.md) section 6 |
| 4 | ontology | `n10s.onto.import.inline` of [data/cdm/cdm.rdf](../data/cdm/cdm.rdf) unless classes are already there | the CDM model (classes, relationships, properties, domains/ranges) is in the database next to the data, so queries and tools can use it |
| 5 | work IDs | reads `data/work_ids.txt`; gathers the list first if it is missing or with `--refresh-ids` | the input of the next phase; `--limit N` takes the first N |
| 6 | documents | for each work ID: download the metadata from Cellar, run the transformer chain, write to Neo4j; one report per document | the actual population; see section 3 |
| 7 | reconcile | merges works that exist twice under different identifiers (`apoc.refactor.mergeNodes`), once at the end | cross-document alias drift (ETL_TRANSFORMER_LOADER_STRATEGY.md section 5); skipped without APOC |
| 8 | labels | sets the English `label` of `:Concept` and `:Institution` nodes from the SPARQL endpoint (`skos:prefLabel`) | the dumps contain only the URIs of EuroVoc concepts and authority table entries; without it the graph shows `eurovoc.europa.eu/4359` |
| 9 | statistics | counts what is in the database and writes `summary.md` / `summary.json` | the numbers for the report |

Decisions worth knowing:

* **The ontology lives next to the data without mixing with it.** n10s labels the ontology nodes with a prefix (`n4sch__Class`,
  `n4sch__Relationship`, `n4sch__Property`) and the relationship types `n4sch__SCO`, `n4sch__DOMAIN` ..., so they cannot collide with
  `:Work`, `:Concept` or `CITES`. The statistics exclude them. Result: 576 classes, 1,700 relationships, 965 properties.
* **Only `cdm.rdf` is imported.** `cdm_annotationproperties.rdf` is parsed by n10s (259 triples) but nothing of it is loaded (annotation
  properties are not part of n10s's model); `--ontology-files` takes other files of `data/cdm/`.
* **Our facts are not written by n10s.** The documents are written by the project's own loader with plain Cypher property and relationship
  names (strategy decision); n10s is used only for the ontology and the configuration. The two worlds meet in the `uri` of `:Resource`.
* **Lifecycle is on by default** (dossiers, events: `IN_PROCEDURE`, `AT_EVENT`, `EVENT_OF` ...); `--no-lifecycle` turns it off. The WEMI level is the work level.
* **`--reset` keeps the constraints and indexes** and deletes every node. The n10s configuration is a node too, so it is created again in phase 3
  (n10s refuses to drop a configuration while there is data, which is why the reset deletes the nodes instead).
* **One failing document does not stop the run**: its error is in its report and in the summary; the run ends with exit code 1.

## 2. Parameters

| Option | Meaning |
| --- | --- |
| `-w, --work-ids-file FILE` | the list to load (default `data/work_ids.txt`) |
| `-r, --refresh-ids` | gather the list again first ([ACQUISITION_STRATEGY.md](ACQUISITION_STRATEGY.md); the list file and its report are overwritten) |
| `-n, --limit N` | load only the first N works |
| `--resume RUN_DIR` | continue in an existing run directory: works with a successful report there are skipped, failed ones are retried |
| `--run-dir DIR` | where the logs and reports go (default `data/population/<local time>`) |
| `--reset` `--yes` | delete all nodes first; `--yes` is required |
| `--no-lifecycle` | skip dossiers and events |
| `--skip-ontology`, `--ontology-files A,B` | skip the ontology / import other CDM files |
| `--skip-labels` | skip phase 8 |
| `--no-reconcile` | skip phase 7 even with APOC |
| `--top N` | keep the N largest entries of each breakdown in the per-document reports (default 50) |
| `-l, --log-level` | `INFO` (default): one line per step and document; `DEBUG`: full breakdowns |
| `--host --port --user --password` | the database (`--password` defaults to `$NEO4J_PASSWORD`) |

Exit codes: `0` completed, `1` completed but some documents failed, `2` the process could not run (usage, database, plugin), `130` interrupted
(Ctrl+C: the run stops at once, finishes the statistics and can be continued with `--resume`; the document that was being written has no report, so it is done again, which is safe because of `MERGE`).

## 3. The documents phase

For every work ID the pipeline of [ETL_PIPELINE.md](ETL_PIPELINE.md) runs with the Cellar extractor: `extract` (metadata request to Cellar) -> the
nine transformer steps -> `load` (projection to nodes and relationships, `UNWIND ... MERGE` in batches of 5,000 rows). The log shows
per document the triples extracted, one line per step and the load counters, then a progress line with an estimate:

```
documents [1/2] 115852e8-... ok in 87.6s (6,516 nodes, 25,010 relationships) - elapsed 0:01:27, remaining about 0:01:27
```

`MERGE` makes the loading **order independent and repeatable**: a work that is first seen as the end of a relation becomes a stub
(`stub = true`) and is completed when its own document is loaded; overlapping documents share their nodes and relationships. The
reports state, per document, how many nodes and relationships were *projected* and how many the database *created* (the difference is what
`MERGE` found already present).

## 4. Logging and reports

Everything of a run goes to its directory `data/population/<time>/` (the loggers `etlpipe.*` and `acquisition`; console and file):

| File | Content |
| --- | --- |
| `populate.log` | the complete log of the run (every phase, every document, every transformer step, warnings, tracebacks) |
| `summary.md` | the report to read: phases and their times, environment, ontology, the documents (counts, triples, time per stage, slowest, failures), database changes, labels, the database after the run (nodes per label, relationships per type, most connected works) |
| `summary.json` | the same as data (every number of the report, the complete label list, the parameters without the password) |
| `aggregate.json` | per-step statistics of the transformer chain summed over the documents of the run (triples in/out, counters such as `duplicates_folded`, breakdowns), graph nodes/edges per type, database counters |
| `documents/<work id>.json` | the complete report of one document: extract, every step, canonical graph, load |
| `documents/runs.jsonl` | one line per document, appended by every invocation (the history of a resumed run) |
| `previous_summaries/` | when a run is resumed, the summary of the earlier invocation is kept here (a resumed run reports only its own work) |

Statistics at three levels: **per document** (`documents/`), **aggregated over the run** (`aggregate.json` and the documents section of
`summary.md`), **of the database** (statistics phase; this one is independent of how the data got there, so it is the total after any
number of resumed runs). The database statistics include `works_duplicated_by_celex`, the number of works stored twice under different
identifiers: it tells whether the reconciliation (APOC) is needed when APOC is not installed.

## 5. Operating it

* **Interrupted or failed documents.** Start again with `--resume <run dir>`: finished works are skipped, failed and unfinished ones are done.
  A plain restart without `--resume` reloads everything (harmless, but slow).
* **Start over.** `--reset --yes` (everything is deleted, the schema is kept) - or erase the database as before; the process also works
  on a database without schema.
* **After changing the transformer or the policy tables** reload with `--reset --yes`: `MERGE` replaces properties but never deletes
  relationships that the new rules would no longer create.
* **A different list.** `--work-ids-file`, or `--refresh-ids` with other parameters through [scripts/data_acquisition](../scripts/data_acquisition).

## 6. A test run

On the empty database (`--reset --yes --limit 2`, with the first two works of the list: Regulation 1/1958 and Regulation 259/68) the process
took 2 min 22 s: ontology 576 classes / 1,700 relationships / 965 properties imported in 1.7 s; two documents (255,877 triples) 133 s
(extract 46 s, transform 52 s, load 33 s); the labels of 1,022 concepts and institutions in 2.6 s; the result 9,982 nodes (3,216 works with
their own metadata, 5,492 stubs, 914 concepts, 108 institutions, 117 dossiers, 114 events) and 38,202 relationships (25,701 `CITES`,
4,032 `IS_ABOUT`, 2,066 `BASED_ON`, 1,775 `AMENDS` ...). A second run with `--resume` skipped both documents and changed nothing.
The unit tests (`python -m unittest scripts.data_load.test_populate`) need neither database nor network.

## 7. Limits

* **The complete population (491 works) has not been run yet**; its duration is an estimate from the first two documents
  ([ACQUISITION_STRATEGY.md](ACQUISITION_STRATEGY.md) section 5). The log gives an estimate of the remaining time after every document.
* **The "works with their own metadata" count is larger than the number of requested works**: the Cellar dump of a document also describes
  the works around it (those that cite it, ...), and those become non-stub nodes too. The summary therefore also says how many of the *requested*
  works are in the database.
* **APOC is not installed in the current database**, so duplicated works would not be merged; the statistics count them (0 in the test run).
* **Concept labels are English only** (`label`); other languages and the EuroVoc hierarchy (SKOS broader/narrower) are not imported.
* **Cellar is called sequentially**, without retries inside a document; a transient failure fails that document, which `--resume` retries.
