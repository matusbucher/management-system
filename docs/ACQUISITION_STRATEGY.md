# Strategy for acquiring the documents of the knowledge graph

How the set of documents to load into Neo4j is chosen, and how the work IDs of that set are gathered **without
downloading any metadata**. The result is [data/work_ids.txt](../data/work_ids.txt), a list of Cellar work UUIDs that is a
ready-to-go input of the ETL pipeline and of the database population ([DATABASE_POPULATION.md](DATABASE_POPULATION.md)):

```powershell
python scripts\data_acquisition\gather_work_ids.py                     # build the list (about 5 minutes, no metadata downloaded)
python scripts\data_load\populate_database.py                          # set up the database and load the listed works
python src\etl_cli.py --work-ids-file data\work_ids.txt --lifecycle    # or: transform only (dry run); add --load to write to Neo4j
```

Code (kept in `scripts/`, it is tooling around the system, not part of it): [scripts/data_acquisition/](../scripts/data_acquisition)
(configuration, gatherer, file format, CLI [gather_work_ids.py](../scripts/data_acquisition/gather_work_ids.py) and tests
[test_acquisition.py](../scripts/data_acquisition/test_acquisition.py)). Everything below was measured against the live services on 2026-11-17.

## 1. Short answer

* Select **by topic and by closeness**, not by a text search: documents tagged with cybersecurity EuroVoc descriptors,
  plus the acts that are *densely linked* to what has been collected. The selection is a **seed → topic → expansion**
  pipeline; each stage is cheap (IDs only) and its result is explainable (every ID in the list says which stage selected it).
* **SPARQL is the workhorse** (set-oriented queries over the whole repository), the **EUR-Lex web service** is an independent
  second opinion on the topic search, and the **Cellar API** resolves identifiers (CELEX/ELI/OJ → work UUID) and is the only
  service used later to download metadata.
* Result with the default parameters: **491 acts** (14 seeds + 206 topic + 282 expansion) joined by **2,695 legal links
  inside the collection**; 486 of the 491 acts have at least one link to another member. Downloading their metadata is
  the only expensive step (several hours of pipeline time, see section 5).
* The size is a dial (`--min-links`, `--rounds`, descriptor lists in [config.py](../scripts/data_acquisition/config.py)); section 5 has the numbers.

## 2. What "good" means here

The knowledge graph is useful for lifecycle and impact questions ("what does NIS 2 repeal, amend, rely on, what relies on it?").
That needs **coherence** more than volume: a document is only valuable if the documents it is related to are also in the
graph, otherwise its relations end in stub nodes. So the selection criteria are, in this order:

1. **Relevance** - the document is about cybersecurity (or the digital trust topics next to it: data protection,
   electronic identification, AI).
2. **Coherence** - the relations between selected documents (amends, repeals, based on, cites ...) are in the collection.
   The report measures it (`stats.coherence`): number of links inside the collection and works without any.
3. **Bounded size** - the run must be repeatable on a laptop; the dials above control it.
4. **Provenance** - for every ID it is recorded why it is there (`stages`, `sources`, `links` in
   [data/work_ids_report.json](../data/work_ids_report.json)).

Deliberate scope: **main legislative acts** (CELEX sector 3 - regulations, directives, decisions, recommendations ...).
Excluded: corrigenda (`32022L2555R(01)`), consolidated texts (`0...`), preparatory documents, case law, national
transposition measures (305 national measures point to NIS 2 alone), and budget acts (see 4.2). They are not lost: when an
included act relates to them the ETL creates *stub* nodes for them (see [ETL_PIPELINE.md](ETL_PIPELINE.md)), and
the legislative procedure (dossier and events, `--lifecycle`) brings the proposal and the adoption steps.

## 3. The three services and what each is used for

| Service | Strength | Limits found while testing | Role |
| --- | --- | --- | --- |
| **SPARQL** (`publications.europa.eu/webapi/rdf/sparql`, [sparql_api.py](../src/eurlex/sparql_api.py)) | any set-oriented question over the whole CDM: topic membership, links between works, CELEX numbers | rejects requests above ~6 KB with HTTP 403 (a `VALUES` list of 80 full URIs fails, 120 prefixed ones work); a join with the CELEX numbers inside a big query takes 10-50 s while the same data in a separate query takes 0.1 s | topic search, expansion, coherence, CELEX numbers |
| **EUR-Lex web service** (SOAP expert query, [webservice_api.py](../src/eurlex/webservice_api.py)) | the "official" search; `DC_CODED = <EuroVoc id>` and `DTS_SUBDOM = LEGISLATION` work | max 100 results per page; **paging through a bigger result is unstable** (4 identical queries for one descriptor returned 285, 263, 276 and 261 documents, only 233 in all four) and `page_size` above 100 is a server error; results are `eng_cellar:<uuid>_en` references | independent cross-check of the topic search |
| **Cellar API** (`publications.europa.eu/resource/...`, [cellar_api.py](../src/eurlex/cellar_api.py)) | the authority for identifiers: the *identifiers notice* of `resource/celex/32022L2555` returns the Cellar UUID and the OJ and ELI synonyms; the only source of the full metadata | one resource per call; metadata is big (up to 64 MB for the GDPR) | resolves the curated seeds; later downloads the metadata in the ETL |

Findings that shaped the design:

* **Both searches agree.** For the 10 core descriptors SPARQL finds 206 acts and the web service finds the same 206 (no
  act found by one only). That is the useful property of a cross-check: the stage is not just "whatever one service returns".
  The report records `both`, `sparql_only`, `webservice_only`; a non-zero `webservice_only` would be a recall gap of the SPARQL query.
* **The web service is made deterministic by slicing.** A descriptor with more than one page of results is queried again once
  per year of the document date (`DD_YEAR = 2020`, the only range form the service accepts), so each query returns far less than 100
  results. Without it the cross-check would drift from run to run.
* **Cellar API needs a CELEX production system.** `CellarPS.CELEX` was added to [cellar_api.py](../src/eurlex/cellar_api.py)
  and `CellarAPI.extract_identifiers` extracts the identifiers from a notice (the "resource ID extraction from outputs").
  If a CELEX number cannot be resolved by the Cellar API, the gatherer falls back to SPARQL.

## 4. The stages

```
curated seeds ──► core set ──► topic (EuroVoc, 2 services) ──► core ──► expansion (links to core) ──► final list
 (CELEX, Cellar)               (SPARQL + web service, deduplicated)        (SPARQL, gated)            data/work_ids.txt
```

### 4.1 Stage 1: seeds (Cellar API)

The 14 acts analysed in [RDF_METADATA_ANALYSIS.md](RDF_METADATA_ANALYSIS.md) (NIS 1/2, DORA, CRA, Cybersecurity Act, eIDAS 1/2,
GDPR, AI Act, CER, Data Governance Act, ENISA and Competence Centre regulations, DORA amending directive), as CELEX numbers in
`SEED_CELEX`. They are always in the list, even if no descriptor matches them (3 of the 14 are in no other stage).

### 4.2 Stage 2: topic (SPARQL + web service, EuroVoc)

The topic is defined by **EuroVoc descriptors**, which are assigned by the indexers of the Publications Office and so do
not depend on the wording of a title (a title search for "cybersecurity" finds 66 legislative documents and cannot find an act such as
DORA, whose title speaks of "digital operational resilience").

**How the descriptors were chosen (data-driven, not guessed).** The EuroVoc tags of the 14 seeds were counted. The most
frequent ones: *data protection* (8 of 14), *information security* (7), *computer crime* (7), *single market* (5), *digital single
market* (4), *personal data* (4), then *critical infrastructure security*, *electronic signature* and *European Union Agency
for Cybersecurity* (2 each). The EuroVoc labels matching cyber/security/digital/crypto terms were then listed and counted over
the repository, and split in two groups:

* **Core descriptors** (`CORE_DESCRIPTORS`) define the topic alone: information security, computer crime, cyber resilience,
  critical infrastructure security, European Union Agency for Cybersecurity, information technology incident, malware,
  cryptography, information warfare, digital evidence. 206 acts.
* **Adjacent descriptors** (`ADJACENT_DESCRIPTORS`) are too broad to define the topic (data protection alone tags 6,375 works
  of all document types): electronic signature, data protection, protection of privacy,
  personal data, digital sovereignty. They are used only in stage 3, as a relaxed link requirement.

Rejected as too broad: *information system* (3,716 works), *digital single market* (1,427), *digital economy*, *computer network*.

**Budget acts are excluded** (`EXCLUDED_ACT_TYPES`): a first run returned 52 budget and supplementary budget acts (CELEX type `B`)
because they are tagged with the descriptor of every agency they fund (ENISA); they are the isolated "topic" documents with no
relation to anything else in the collection and carry no legal content.

### 4.3 Stage 3: expansion by closeness (SPARQL)

The topic search finds documents *about* cybersecurity, but the amending act of a regulation or the basic act it is based on need
not be tagged with a cybersecurity descriptor. The expansion adds the acts that are **linked to the documents collected so far**:

* relations followed, in both directions (`EXPANSION_RELATIONS`): *amends*, *repeals*, *based on*, *implements*, *corrects*, *adopts*, *cites*;
* an act is added when it is linked to **at least `--min-links` (default 3) collected works**, **or** to at least one and tagged with an
  adjacent descriptor (a data protection act that is cited by a cybersecurity act belongs in the graph; a data
  protection act that nothing in the collection mentions does not);
* only main acts count, and only works that are not collected yet.

Why a link *count* and not "any link": in the default run 4,352 works of every type are linked to the 209 collected ones,
1,025 of them main acts, the majority by a single citation. Taking every linked act would give 1,234 acts (6 times the core)
and dilute it (legislative hubs such as the Financial Regulation are cited by everything). Requiring several links keeps the
acts that are structurally close to the core. Typical additions (links to the collection): Regulation 2018/1725 on data
protection in the Union institutions (77), the ePrivacy Directive 2002/58 (46), the Galileo/EU Space Programme Regulation 2021/696
(16), the ESMA/EBA/EIOPA founding regulations 1093-1095/2010 (11-14), the Law Enforcement Directive 2016/680 (13).

`--rounds N` repeats the expansion; with rounds above 1 the new acts become part of the core for the next round (a snowball,
which grows quickly; the default is 1).

### 4.4 Stage 4: coherence report

After the last stage the gatherer counts the links between members (one chunked query, no join explosion) and writes into the report:

| Metric (default run) | Value |
| --- | --- |
| acts | 491 (types: 257 regulations, 157 decisions, 51 directives, 17 recommendations, 9 others) |
| links inside the collection | 2,695 (2,316 cites, 208 based on, 145 amends, 26 repeals) |
| acts with at least one link inside | 486 of 491 |
| isolated acts | 5 (a common position, 31999F0364, and four decisions) |
| document years | 1958 - 2026, 84 % from 2015 on |

A collection of 491 acts with 2,695 internal links has 5.5 internal links per act. The isolated acts are listed in
`stats.coherence.isolated` and can be removed by hand; no automatic pruning is done because an isolated *seed* may still be wanted.

## 5. Dials and sizes

Measured on the same collected core (209 acts = 14 seeds + 206 topic - 11 seeds that are also in the topic):

| `--min-links` | links only | with adjacent single-link acts (default) |
| --- | --- | --- |
| 1 | 1,234 acts | 1,234 |
| 2 | 521 | 640 |
| **3** | 353 | **491** |
| 4 | 287 | 441 |
| 5 | 256 | 415 |
| 7 | 233 | 399 |

* A **small, tight** graph for development: `python scripts\data_acquisition\gather_work_ids.py -x` (no expansion: seeds + topic, 209 acts); `-m 7` gives 399.
* The **default** (491 acts) is the proposed volume for the thesis graph.
* A **wide** graph: `-m 2` (640 acts) or `-n 2` (second round).
* Different topic: edit `SEED_CELEX` and the descriptor tables - the rest is generic.

Cost of loading: the 14 analysed documents average 9 MB of RDF/XML (73,000 triples). Measured end to end (download from Cellar,
transform, write to Neo4j) the first two documents of the list, two of the largest (164,000 and 92,000 triples), took 88 s and 46 s, so the
full list is a matter of **several hours** (a few hours if the typical act is much smaller than those two) and a few GB of transfer, none of
it stored. The load is idempotent (`MERGE`) and `populate_database.py --resume` continues where an interrupted run stopped; `--limit N` loads
only the first N works of the list.

## 6. Files

| File | Content |
| --- | --- |
| [data/work_ids.txt](../data/work_ids.txt) | one work UUID per line with a comment `# <CELEX>  <stages>`; `#` lines and blank lines are ignored |
| [data/work_ids_report.json](../data/work_ids_report.json) | parameters, statistics (`seeds`, `topic` cross-check, `expansion` rounds, `by_stage`, `coherence`) and per-work provenance |
| [data/analysis/documents/](../data/analysis/documents) | the 14 RDF/XML dumps used for the analysis (moved from `data/`; the scripts and docs were updated) |

Command line (`python scripts\data_acquisition\gather_work_ids.py -h`): `-o` output list, `-r` report, `-m` minimum links, `-n` expansion rounds,
`-x` no expansion, `-w` skip the web service (it needs the SOAP template with credentials in `templates/`), `-l` log level.

## 7. Limits and open points

* **Topic coverage is as good as the EuroVoc indexing.** Documents without a descriptor (very recent acts are indexed late) are found only through
  the expansion or the seeds. The cross-check with the web service helps only against SPARQL query mistakes, not against missing tags.
* **Citations dominate the links** (86 %). A *cites* link is weaker evidence of closeness than *amends*/*repeals*, but dropping it would
  isolate the legislative-hub acts. `EXPANSION_RELATIONS` is the place to tighten the rule (for example count only the structural relations).
* **Only acts are collected.** Proposals (COM documents), opinions and case law are reachable through the dossier/event lifecycle
  and through stubs, but are not loaded as full documents. A second list of the same kind (for instance CJEU judgments on NIS/GDPR) would be a
  new source in the same format.
* **Expansion only follows the relations of the CDM listed above.** *Consolidated* versions and *national implementing measures* are intentionally not followed.
* **No snapshot of the services.** The repository changes daily (new acts, new tags); the report records the date and the parameters, and the
  list should be regenerated and diffed before a reload rather than edited by hand.
* **The SPARQL size limit (~6 KB) is a property of the public endpoint, not of the protocol**; the gatherer splits every long
  list in chunks of 50 IDs. A self-hosted endpoint would not need it.
