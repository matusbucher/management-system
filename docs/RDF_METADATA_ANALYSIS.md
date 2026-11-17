# EUR-Lex Cellar RDF metadata – analysis for a work-level transformer

Analysis of the RDF/XML dumps in `data/` (14 files, 1,030,506 triples, 125 MB) fetched by [cellar_base.py](../test/cellar_base.py)
through `CellarAPI.metadata_request`. The goal is to decide which triples belong to the **Work level of the WEMI
hierarchy** (and to the knowledge-management graph in Neo4j) and which can be dropped or folded before loading.
No transformer is implemented here – only the analysis tooling and the rules a transformer should follow.

Companion artefacts:

| Artefact | Purpose |
|---|---|
| [scripts/rdf_analysis/](../scripts/rdf_analysis) | reproducible analysis scripts (see [§8](#8-reproducing-the-analysis)) |
| [rdf_analysis/predicate_classification.csv](rdf_analysis/predicate_classification.csv) | all 331 predicates found in the dumps with CDM level, usage, category and proposed action |
| [rdf_analysis/type_classification.csv](rdf_analysis/type_classification.csv) | all 95 `rdf:type` classes with proposed action |
| [rdf_analysis/summary.json](rdf_analysis/summary.json) | machine-readable totals quoted below |
| [RDF_TRIPLES_GUIDE.md](RDF_TRIPLES_GUIDE.md) | short explanation of the triple patterns in the dumps, with real examples |

---

## 1. Key findings

1. **The dumps are almost purely Work-level.** No subject is a manifestation or item, and none of the 331 predicates is
   declared for the Expression, Manifestation or Item level (some hub properties have such sub-properties, see §5.4).
   The only "other WEMI" content is the 335 language-suffixed expression URIs (`….LIT`) with their 335 `cdm:work_has_expression` links and
   40,699 `annot:language_list` values – 4.0 % of all triples, all droppable. (The 3,006 `cellar/<uuid>.NNNN` nodes that look like expressions are
   **events and sittings of legislative procedures**, see [ETL_PIPELINE.md §5](ETL_PIPELINE.md#5-document-lifecycle---lifecycle); they are kept when lifecycle tracking is on.)
2. **The real size/noise problem is not WEMI, it is RDF plumbing:**
   * 39 % of the triples (400,382) sit in blank nodes – 53,210 `owl:Axiom` reification nodes that annotate relations;
   * 23 % (232,100 triples) are *materialised inference*: every relation is asserted twice (specific CDM property +
     generic super-property, e.g. `cdm:work_cited_by_work` **and** `cdm:cited_by`);
   * 14 % (145,240) are `owl:sameAs` alias links (the same work appears under 4–6 URIs).
3. **Identity and data are spread over alias nodes.** For one work, the CELEX node holds the *incoming* relations (`cited_by`,
   `implemented_by`, `basis_for`, `consolidated_by`…), the OJ node (`oj/…`) holds the work's *own* attributes and *outgoing* relations
   (`cites`, `amends`, `repeals`, `is_about`, dates, identifiers), the `cellar/<uuid>` node only Cellar timestamps and the `sameAs`
   links, and the `eli/…` node nothing. Alias resolution through `owl:sameAs` is the mandatory first transformation step.
4. **The dump is a relation neighbourhood, not a full notice.** For the requested ("focal") work there are only
   284–5,538 own triples; there is **no title** (`cdm:work_title`/`cdm:title` occur 3 times each, in total) because titles are
   Expression-level in CDM (`cdm:expression_title`). Titles/labels, if wanted in the KMS, need a separate expression-level
   fetch. The bulk of each file is *other* works pointing at the focal work (`cdm:cited_by`, `cdm:basis_for`, …).
5. **All 14 files are now the documents they are named after** (verified with `inspect_focal.py`, see [§2.2](#22-data-quality-problems-in-the-input)).
6. **Cross-file overlap is large.** 453,163 relation triples collapse to 224,351 unique edges per file and
   **142,535 unique edges overall** (−69 %) once aliases, super-property duplicates and inverse directions are folded;
   43,094 edges (30 %) occur in more than one file. Without normalisation the same edge would be loaded repeatedly under
   different alias URIs/directions.
7. **72 % of the unique citation edges (62,752 of 87,001 `cited_by`) come from preparatory acts** (COM/SWD documents,
   CELEX sector 5) and another 7,508 from case-law; only 12,658 come from legislation. Scope filtering by source
   document type is a decision with a large effect on graph size.

---

## 2. Input data

### 2.1 Files

`triples` counts are rdflib triples. "own" = triples whose subject is any alias of the requested Cellar ID.
"edges" = CDM object-property triples (`raw`) and the unique edges they fold into per file (§3, `edge_overlap.py`).

| File | Size MB | Triples | URI subjects | Blank-node subjects | Predicates | Focal CELEX | own | edges raw → unique |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| AI-Act | 4.7 | 36,622 | 7,747 | 660 | 217 | 32024R1689 | 848 | 20,918 → 10,266 |
| CER-Directive | 5.5 | 44,659 | 6,774 | 2,392 | 201 | 32022L2557 | 1,005 | 18,329 → 8,980 |
| Cyber-Resilience-Act | 2.3 | 17,666 | 3,741 | 407 | 200 | 32024R2847 | 510 | 9,154 → 4,460 |
| Cybersecurity-Act | 4.9 | 39,714 | 6,246 | 1,527 | 205 | 32019R0881 | 652 | 19,714 → 9,749 |
| Data-Governance-Act | 2.3 | 17,971 | 3,936 | 251 | 179 | 32022R0868 | 435 | 10,475 → 5,220 |
| DORA-Amending-Directive | 1.9 | 16,339 | 1,295 | 1,408 | 162 | 32022L2556 | 806 | 4,094 → 2,045 |
| DORA | 2.3 | 18,033 | 3,478 | 637 | 190 | 32022R2554 | 544 | 8,713 → 4,226 |
| eIDAS-1 | 12.3 | 105,077 | 13,652 | 3,172 | 220 | 32014R0910 | 1,421 | 57,085 → 28,292 |
| eIDAS-2 | 1.7 | 13,587 | 2,416 | 507 | 173 | 32024R1183 | 376 | 5,938 → 2,926 |
| ENISA-Reg-526-2013 | 1.5 | 12,066 | 2,441 | 288 | 164 | 32013R0526 | 310 | 4,762 → 2,377 |
| EU-Cybersecurity-Competence-Centre-Regulation | 1.0 | 7,852 | 2,005 | 133 | 147 | 32021R0887 | 284 | 4,002 → 1,989 |
| GDPR | 63.8 | 528,338 | 39,334 | 33,745 | 259 | 32016R0679 | 5,538 | 208,582 → 103,361 |
| NIS1 | 11.5 | 98,460 | 12,083 | 4,000 | 199 | 32016L1148 | 1,237 | 48,860 → 24,389 |
| NIS2 | 8.9 | 74,122 | 8,907 | 4,083 | 205 | 32022L2555 | 1,416 | 32,537 → 16,071 |

GDPR alone is 51 % of all triples; it is dominated by case-law and preparatory-act citations.

---

## 3. Method

* **CDM ontology index** ([cdm_ontology.py](../scripts/rdf_analysis/cdm_ontology.py)): loads [docs/cdm/cdm.rdf](cdm/cdm.rdf) and
  `cdm_annotationproperties.rdf`; assigns every class and property a WEMI level from `rdfs:subClassOf` chains to
  `cdm:work|expression|manifestation|item` and from `rdfs:domain`; records super/sub-properties, inverses, and the CDM's own
  comment flag *"Relevant for legal analysis: true"* (336 properties; 78 of the 331 used ones).
  Properties without a domain but with sub-properties are *generic* (hub) properties – their level depends on the subject.
* **Profiling** ([profile_rdf.py](../scripts/rdf_analysis/profile_rdf.py)): every subject gets a WEMI level by, in order,
  Cellar URI structure (`cellar/<uuid>` = W, `.NNNN` = E, `.NNNN.NN` = M, `/DOC_n` = I) → `rdf:type` → URI language suffix →
  domain of the properties it uses. Counters per (subject level, predicate, object kind) are stored as JSON.
* **Classification** ([classify_predicates.py](../scripts/rdf_analysis/classify_predicates.py)) combines ontology level, observed
  usage (subject level, object kind, share of duplicated triples) and a small set of explicit decisions (edge annotations,
  legal-relation roots) into a category and action for every term.
* **Edge normalisation experiment** ([edge_overlap.py](../scripts/rdf_analysis/edge_overlap.py)) measures how many relations survive
  alias resolution, super-property folding and inverse folding.

---

## 4. Anatomy of the dumps

### 4.1 Resource (subject) families

Distinct subjects, summed over files (the same work recurs across files):

| Family | Subjects | WEMI role |
|---|---:|---|
| `cellar/<uuid>` | 48,550 | Work (one URI of the alias group) |
| `celex/…` | 42,831 | Work alias – carries most relations |
| `eurovoc/…` (`http://eurovoc.europa.eu/…`) | 3,636 | vocabulary concept (not WEMI) |
| `oj/…` | 3,424 | Work alias (Official Journal) |
| `cellar/<uuid>.NNNN` | 3,006 | **not an expression**: Cellar's id of an event / sitting of a procedure (`owl:sameAs` of `procedure-event/…`, `session-sitting/…`) |
| `authority/<table>/<code>` | 2,013 (+14 tables) | reference data (institutions, countries, resource types…) |
| `procedure-event`, `procedure`, `internal_proc*`, `session*`, `case*`, `dossier`, `intproc*` | ≈ 4,910 | non-WEMI CDM entities (procedure, event, dossier, case) – mostly untyped |
| `comnat`, `immc`, `nim`, `consil`, `consolidation`, `ep`, … | ≈ 5,430 | Work aliases of specific document families (plus 236 `agent` URIs) |

Subject levels after inference: **work 100,225** (48,550 by URI structure, 41,844 by predicate domain, 9,831 by `rdf:type`),
vocabulary 5,663, untyped (events/dossiers/procedures) 5,161, URI-structure "expression" 3,006 (in fact events, see above), **manifestation 0, item 0**.

### 4.2 Alias groups (`owl:sameAs`)

A work is typically 4 URIs: `cellar + celex + eli + oj` (20,389 groups), `cellar + celex + comnat + immc` (6,356), `cellar + celex + ecli`
(4,508; case-law), `cellar + celex + oj` (3,587) … Groups range from 2 to more than 50 members. Groups with an expression member are
`cellar/<uuid>.NNNN ↔ procedure-event/…` and carry no work information.

### 4.3 Reification (blank nodes)

Relations are annotated through OWL axioms:

```
_:b a owl:Axiom ; owl:annotatedSource res:celex/32024R1689 ;
    owl:annotatedProperty cdm:work_cited_by_work ;
    owl:annotatedTarget res:celex/62024CO0806 ;
    annot:fragment_citing_source "N 5" ; annot:fragment_cited_target "A95P2" ; annot:build_info "reception-ID: …" .
```

* 53,210 axioms; 51,181 are well-formed, **2,029 are "headless"** (no `annotatedSource/Property/Target`) – amendment records
  with `reference_to_modified_location`, `impact`, `type_instruction`, `start_of_validity` that cannot be attached to any edge and
  can only be dropped (or matched heuristically).
* Most axioms (≈ 97 % in a sample of four files) name only the specific property in `owl:annotatedProperty`; axioms on outgoing
  `amends`/`adopts`/`repeals` relations and on dates also list the generic super-properties (e.g. `cdm:date`, `cdm:date_deadline`,
  `cdm:resource_legal_date_deadline`). An axiom has to be matched to its edge by *any* of the listed properties. One axiom exists per relation, not per triple.
* Which relations carry payload: `cited_by` (citation fragments), `amended_by`/`amends` (modified location, role, validity, link type),
  `implemented_by` (transposition deadline/notification of national measures), `basis_for` (article/paragraph/sub-paragraph/ELI of the
  legal basis), `repealed_by`, `adopted_by`, `implicitly_repealed_by` (validity, link type).

### 4.4 Literals

Only 1,108 literals exist outside axioms (193,024 sit inside axioms): `xsd:string` 466, `xsd:date` 357, `positiveInteger` 94, `boolean` 76,
`anyURI` 42, `gYear` 31, `dateTime` 29, a few others. There are no language-tagged literals. Sentinel/placeholder values occur: `"$BUILD_INFO$"`, `1001-01-01` (unknown date), `TO_VALIDATE`, and inline vocabulary markers such as
`{J|http://publications.europa.eu/resource/authority/fd_375/J}` in `annot:role2` / `annot:reference_to_modified_location` /
`annot:comment_on_date` that must be parsed to a plain code.

---

## 5. Work level vs. everything else

### 5.1 Triple budget by proposed treatment

Totals over all 14 files (1,030,506 triples):

| Category | Triples | Share | Action |
|---|---:|---:|---|
| Work ↔ work legal relations (specific properties) | 174,074 | 16.9 % | **KEEP** (as edges) |
| Generic duplicates of those relations / attributes | 187,100 | 18.2 % | **FOLD** into the specific/canonical property |
| Work ↔ EuroVoc / subject-matter / directory-code / Treaty basis | 48,515 | 4.7 % | **KEEP** (links to concept nodes) |
| Work ↔ institution (created by, responsible for) | 23,055 | 2.2 % | **KEEP** (links to institution nodes) |
| Work attributes (id, dates, in-force, eli, year, type…) | 444 | <0.1 % | **KEEP** (node properties) |
| Work ↔ dossier/event/procedure/OJ/case-actors context | 20,711 | 2.0 % | OPTIONAL (decide scope) |
| `owl:sameAs` (141,798 on work URIs, 3,442 on cellar `.NNNN` event ids) | 145,240 | 14.1 % | **FOLD** into identifiers of one Work node (events: into the event node) |
| `rdf:type` (53,210 are `owl:Axiom`) | 83,548 | 8.1 % | KEEP-FILTERED (document type only) |
| Reification structure (`annotatedSource/Property/Target`) | 153,972 | 14.9 % | **FOLD** (becomes relationship properties) |
| Edge annotations – semantic payload (§5.3) | 130,383 | 12.7 % | **KEEP** as relationship properties |
| Edge annotations – technical (`language_list`, `build_info`…) | 62,829 | 6.1 % | DROP |
| Work → expression link | 335 | <0.1 % | DROP (hierarchy plumbing) |
| SKOS `inScheme`, Cellar timestamps | 300 | <0.1 % | OPTIONAL |

The exact predicate lists behind each row are in [predicate_classification.csv](rdf_analysis/predicate_classification.csv)
(`category`, `action`, `rationale` columns).

### 5.2 Work-level – what to keep

**Identity and typing**

* `owl:sameAs` between work URIs → properties `celex`, `cellarId`, `eli`, `ojId`, `comnat`, … on one node. Drop sameAs whose subject is an
  expression or non-work entity.
* `rdf:type`: keep the most specific work class (`cdm:regulation`, `cdm:directive`, `cdm:regulation_implementing`, `cdm:regulation_delegated`,
  `cdm:act_consolidated`, `cdm:measure_national_implementing`, `cdm:judgement`, `cdm:proposal_*`, …; 56 classes, 6,100 triples) as `docType`.
  Drop technical super-classes `cdm:work`, `cdm:resource_legal`, `cdm:act_preparatory`, `cdm:legislation_secondary`, `cdm:evolutive_work`,
  `cdm:serial_work`, `cdm:complex_work` (23,042 triples, no information).

**Attributes (node properties)** – only present for the focal work, therefore sparse (10–14 files each):
`resource_legal_id_celex`, `work_id_document`, `resource_legal_id_sector`, `resource_legal_type`, `resource_legal_year`,
`resource_legal_number_natural(_celex)`, `resource_legal_eli`, `resource_legal_in-force`, `resource_legal_date_entry-into-force`,
`resource_legal_date_end-of-validity`, `resource_legal_date_signature`, `resource_legal_date_deadline`, `work_date_document`,
`work_date_creation_legacy`, `directive_date_transposition`, `resource_legal_repertoire`, `resource_legal_eea`, `work_version`,
`resource_legal_codified_version`, `resource_legal_information_miscellaneous`/`comment_internal`. Title is **not available**.

**Legal relations between works (edges)** – canonical relation types after folding (unique edges over all files):

| Relation (CDM root) | Unique edges | Notes |
|---|---:|---|
| `cited_by` / `cites` | 87,001 | 72 % of sources are preparatory acts; carries `fragment_citing_source/cited_target` |
| `based_on` / `basis_for` | 6,473 | legal basis; carries article / paragraph / subparagraph / ELI |
| `implemented_by` / `implements` | 6,156 | national implementing measures with transposition dates |
| `related_to` | 955 | generic "related" link |
| `consolidated_by` / `consolidates` | 610 | link to consolidated versions |
| `amendment_proposed_by` | 579 | |
| `is_another_publication_of` | 578 | |
| `amended_by` / `amends` | 496 | carries modified location, role, validity |
| `implicitly_repealed_by`, `repealed_by` | 386, 282 | |
| `adopted_by`, `has_successor`, `interpreted_by`, `influenced_by` | 326, 300, 187, 146 | |
| `corrected_by`, `completed_by`, `replaced_by`, `stated_by`, `derogated_by` | 72, 61, 49, 21, 7 | |

Together ≈ 132k of the 142.5k unique edges are in KEEP-type relations.

**Links to reference entities** – `subject_of`/`is_about` (EuroVoc, subject-matter, directory-code; 18,188 edges), `created_by` /
`creates` and `responsibility_of` / `responsible_for` (institutions; 8,614 edges), Treaty legal basis (`concept_treaty_*`; 1,303 triples). These should become edges to
`Concept` / `Institution` nodes; their labels are not in the dumps (authority entries only have `rdf:type`/`skos:inScheme`).

### 5.3 Edge annotations – keep vs. drop

| Keep as relationship property | Meaning |
|---|---|
| `article`, `paragraph`, `subparagraph`, `eli_target`, `comment_on_legal_basis` | exact location in the legal basis |
| `fragment_citing_source`, `fragment_cited_target` | exact citation fragments |
| `reference_to_modified_location`, `reference_to_modifying_location` | amendment granularity (e.g. `ART:8 PAR:1 PNT:e`) |
| `start_of_validity`, `end_of_validity` | validity of an amendment / repeal / adoption |
| `type_of_link_target`, `role2`, `impact`, `type_instruction` | qualifier of the relation |
| `transposition_deadline_transmitted`, `transposition_notification` | transposition tracking |
| `date`, `type_of_date`, `comment_on_date`, `result_decision` | dates / outcomes |

| Drop | Why |
|---|---|
| `language_list` (40,699) | languages concerned by a link – expression availability |
| `build_info` (20,206) | Cellar ingestion provenance |
| `production_sequence`, `error_message`, `quality_issue`, `order`, `changed_to_identifier` | technical / data-quality notes |
| headless axioms (2,029) | cannot be attached to a relation |

### 5.4 Non-work and other WEMI content – what to drop

| Content | Triples | Reason |
|---|---:|---|
| `cellar/<uuid>.NNNN` event id (with its `sameAs`) | 3,442 | looks like an Expression but is an event/sitting of a procedure; merged into the event node (kept with `--lifecycle`) |
| `cdm:work_has_expression` | 335 | Work→Expression link |
| `annot:language_list` | 40,699 | language availability of a link |
| Manifestation / Item content | 0 | not present in these dumps |
| Authority entries (`authority/*`) beyond `rdf:type`, `skos:inScheme` | – | reference data; labels absent |
| Case-law actor links (`defends_in`, `delivers`, `requests`, `comments`, `reports_on`…) | within the 6,176 `work-context-entity` triples | person/court roles on case-law; outside legislation scope |
| Dossier/event/procedure membership (`contains`, `part_of` dossier/event, `initiated_by`…) | ≈ 12,750 | CDM non-work entities; keep only if procedure tracking is wanted |

Hub properties (`cdm:date`, `cdm:title`, `cdm:type`, `cdm:identifier`, `cdm:has`, `cdm:contains`…) are declared without a domain and
have sub-properties on Work *and* Expression/Manifestation/Item. **Their level must be decided from the subject, never from the property
name or namespace** – in a richer dump the same generic predicate would appear on expressions.

### 5.5 Materialised inference (fold)

232,100 triples are super-property duplicates; the largest are `work_cited_by_work`→`cited_by` (148,922), `concept_eurovoc_subject_of_work`→`subject_of`
(17,067), `agent_creates_work`→`creates` (10,128), `resource_legal_implemented_by_measure_national_implementing`→`implemented_by` (9,245),
`resource_legal_basis_for_resource_legal`→`basis_for` (7,186). Inverse duplicates inside one file are rare (64),
but across files the same fact appears as `A cites B` in one file and `B cited_by A` in another – hence the need to pick **one canonical
direction per inverse pair** (a table maintained by hand; the automatic folding in `edge_overlap.py` is approximate because a few roots
such as `contains`/`part_of`, `based_on`/`basis_for` have several inverse candidates).

---

## 6. Proposed transformer rules (specification, not implemented)

Order matters:

1. **Parse** with rdflib (RDF/XML, 63 MB GDPR parses in ~25 s) or a streaming reader; the format is a flat list of `rdf:Description`s.
2. **Resolve aliases**: union-find over `owl:sameAs`; canonical key = CELEX → Cellar UUID → first URI; keep all aliases as properties
   (`celex`, `cellarId`, `eli`, `oj`).
3. **Assign WEMI level per resolved node** (Cellar URI structure → `rdf:type` → predicate domain; §3) and keep `work`; set
   `expression/manifestation/item` aside (drop). Keep `vocabulary` nodes (EuroVoc/authority) only as targets of kept relations.
4. **Filter predicates** with [predicate_classification.csv](rdf_analysis/predicate_classification.csv): keep `KEEP`, `KEEP-FILTERED`, `KEEP-FOLD`,
   `KEEP-EDGE-PROPERTY`; fold `FOLD`; drop `DROP`; `OPTIONAL` by configuration.
5. **Canonicalise relations**: among all asserted properties for one `(s, o)` pair keep the most specific, name the edge by the
   class-neutral root (`cited_by`, `amended_by`, …) and normalise inverse pairs to one direction (e.g. always `(:Act)-[:AMENDS]->(:Act)`).
6. **Flatten reification**: join each `owl:Axiom` to its edge through `(annotatedSource, annotatedProperty, annotatedTarget)` after alias
   resolution and copy the whitelisted `annot:*` values (§5.3) to the relationship; drop headless axioms; clean placeholders
   (`{CODE|URI}` → `CODE`, `$BUILD_INFO$`, `1001-01-01`, `TO_VALIDATE`).
7. **Reduce types** to a single `docType` (most specific work class).
8. **De-duplicate across files** by `(canonical source, relation, canonical target)`; merge edge properties.
9. **Scope filter (decision needed)**: e.g. restrict `cited_by` sources to legislation + consolidated texts + NIMs and drop
   preparatory acts/case-law, or keep them with a `sourceKind` property derived from the CELEX sector (3 legislation, 5 preparatory,
   6 case-law, 7 national implementing measure, 0 consolidated).

Sketch of the resulting graph: `(:Work {celex, cellarId, eli, docType, year, inForce, dateEntryIntoForce, …})`,
`(:Work)-[:CITES|AMENDS|REPEALS|BASIS_FOR|IMPLEMENTS|CONSOLIDATES… {article, paragraph, modifiedLocation, startOfValidity, …}]->(:Work)`,
`(:Work)-[:IS_ABOUT]->(:Concept {uri, scheme})`, `(:Work)-[:CREATED_BY]->(:Institution {code})`.

---

## 7. Open points for the author

* Keep running `inspect_focal.py` after every fetch (§2.2) – a wrong Cellar ID still yields valid-looking RDF.
* Titles/labels are Expression-level – decide whether to fetch one expression (e.g. ENG) per work, or use the EUR-Lex Web Service
  search results already used elsewhere in the project.
* Decide the scope of citation edges (§6 step 9) and whether dossier/procedure/event context is wanted.
* Define the canonical direction table for inverse relations (≈ 25 relations).
* The dumps contain no per-article structure; fragment strings (`ART:8 PAR:1 PNT:e`) are the only article-level information and
  could later be linked to a document-structure layer.

---

## 8. Reproducing the analysis

Python 3 with `rdflib` (already installed). From the repository root:

```powershell
python scripts\rdf_analysis\profile_rdf.py          # parses data\*.rdf  -> data\analysis\profile\*.json (cached; --force to redo)
python scripts\rdf_analysis\inspect_focal.py --json data\analysis\focal.json   # focal work per file, §2.2
python scripts\rdf_analysis\edge_overlap.py         # edge folding experiment -> data\analysis\edges.json, §1/§5
python scripts\rdf_analysis\classify_predicates.py  # -> docs\rdf_analysis\*.csv, summary.json
```

| Script | Role |
|---|---|
| [cdm_ontology.py](../scripts/rdf_analysis/cdm_ontology.py) | CDM class/property → WEMI level, hierarchy, inverse, legal-relevance flag |
| [profile_rdf.py](../scripts/rdf_analysis/profile_rdf.py) | per-file profile (subject levels, predicate usage, reification, duplicates, alias groups) |
| [inspect_focal.py](../scripts/rdf_analysis/inspect_focal.py) | focal-resource check against [test/cellar_base.py](../test/cellar_base.py) |
| [edge_overlap.py](../scripts/rdf_analysis/edge_overlap.py) | alias/super-property/inverse folding and cross-file overlap |
| [classify_predicates.py](../scripts/rdf_analysis/classify_predicates.py) | category + action per predicate and class; rules and whitelists live here |
