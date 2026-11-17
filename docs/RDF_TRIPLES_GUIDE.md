# Guide to the RDF triples in the Cellar metadata dumps

Short reference for reading the RDF/XML files in `data/analysis/documents/` (output of `CellarAPI.metadata_request`). All examples are real triples taken
from those files (NIS2, AI-Act, NIS1); long literals are cut. Statistics and the keep/drop decisions are in
[RDF_METADATA_ANALYSIS.md](RDF_METADATA_ANALYSIS.md).

## 1. Reading the files

A dump is one flat RDF/XML document: a list of `rdf:Description` elements, each holding all triples of one subject.

```xml
<rdf:RDF xmlns:j.0="http://publications.europa.eu/ontology/cdm#" xmlns:j.3="http://publications.europa.eu/ontology/annotation#" …>
  <rdf:Description rdf:about="http://publications.europa.eu/resource/celex/32022L2555">
    <j.0:cited_by rdf:resource="http://publications.europa.eu/resource/comnat/SWD_2023_0697_FIN"/>
    <j.0:work_cited_by_work rdf:resource="http://publications.europa.eu/resource/comnat/SWD_2023_0697_FIN"/>
    <j.0:in-force rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">true</j.0:in-force>
  </rdf:Description>
```

The `j.0`, `j.1`, … prefixes are generated per file and **are not stable** (`j.1` is `euvoc` in one file and `skos` in another) – always
resolve them through the `xmlns` declarations (rdflib does this). Below, triples are written as `subject predicate object` with these prefixes:

| Prefix | Namespace | Used for |
|---|---|---|
| `cdm:` | `http://publications.europa.eu/ontology/cdm#` | the EU Common Data Model (classes, relations, attributes) |
| `annot:` | `http://publications.europa.eu/ontology/annotation#` | annotations attached to a relation |
| `cmr:` | `http://publications.europa.eu/ontology/cdm/cmr#` | Cellar system timestamps |
| `owl:`, `rdf:`, `skos:`, `xsd:` | W3C | alias links, typing, reification, concepts, datatypes |
| `res:` | `http://publications.europa.eu/resource/` | shortcut for resource URIs in this guide |

A triple's **object** is either a resource (another URI) or a literal (string, date, boolean…). A subject can also be a blank node
(`rdf:nodeID="A0"`) – used only for the reification axioms in §4.8.

## 2. Resource URIs

One work is known under several URIs, one per identifier scheme:

| URI | Example | Meaning |
|---|---|---|
| `res:cellar/<uuid>` | `res:cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1` | Cellar's internal id of the work |
| `res:celex/<id>` | `res:celex/32022L2555` | CELEX number (NIS2) |
| `res:oj/<id>` | `res:oj/JOL_2022_333_R_0002` | Official Journal publication |
| `res:eli/…` | `res:eli/dir/2022/2555/oj` | European Legislation Identifier |
| `res:comnat/…`, `res:consil/…`, `res:nim/…`, `res:consolidation/…` | `res:comnat/SWD_2023_0697_FIN`, `res:nim/202503772` | Commission document, Council document, national implementing measure, consolidated version |
| `res:cellar/<uuid>.0007` | `res:cellar/7e075fd8-34e9-11ed-9c68-01aa75ed71a1.0007` | looks like an expression, but in these dumps it is the id of an *event* or sitting of a procedure (alias of `procedure-event/…`); real expressions are `….LIT`-style language URIs |
| `res:authority/<table>/<code>` | `res:authority/resource-type/DIR` | reference data (institutions, countries, resource types, subject matters) |
| `http://eurovoc.europa.eu/<id>` | `http://eurovoc.europa.eu/4420` | EuroVoc thesaurus concept |

CELEX encodes sector, year, type and number: `3 2022 L 2555` = sector 3 (legislation), 2022, **L**-directive, no. 2555.

## 3. Naming of CDM predicates

CDM properties come in a generic and one or more specific forms, and most relations have an inverse:

| Pattern | Example | Meaning |
|---|---|---|
| `cdm:<name>` (generic) | `cdm:cited_by`, `cdm:date`, `cdm:identifier` | umbrella property, valid at any WEMI level |
| `cdm:work_<name>` | `cdm:work_cited_by_work`, `cdm:work_date_document` | specific property whose domain is a **Work** |
| `cdm:resource_legal_<name>` | `cdm:resource_legal_amends_resource_legal` | specific property of a legal resource (a kind of Work) |
| `cdm:<class>_<name>_<class>` | `cdm:agent_creates_work`, `cdm:concept_eurovoc_subject_of_work` | specific property named after domain and range |
| inverse pair | `cited_by` ↔ `cites`, `amended_by` ↔ `amends`, `basis_for` ↔ `based_on` | the same fact seen from the other end |

The dumps assert both the specific and the generic form for the same pair (materialised inference):

```
res:celex/32022L2555  cdm:work_cited_by_work  res:comnat/SWD_2023_0697_FIN
res:celex/32022L2555  cdm:cited_by            res:comnat/SWD_2023_0697_FIN
```

## 4. Triple patterns

### 4.1 Identity – `owl:sameAs`

All URIs of one work are tied together; the CELEX/OJ/ELI identifiers of a work are found here.

```
res:cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1  owl:sameAs  res:celex/32022L2555
res:cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1  owl:sameAs  res:oj/JOL_2022_333_R_0002
res:cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1  owl:sameAs  res:eli/dir/2022/2555/oj
```

The data of the *same* work is split across these URIs: the CELEX node holds incoming relations, the OJ node the work's own attributes and
outgoing relations, the Cellar node only the timestamps (§4.9), the ELI node nothing. Resolve the group before reading anything else.

### 4.2 Typing – `rdf:type`

```
res:oj/JOL_2022_333_R_0002  rdf:type  cdm:work
res:oj/JOL_2022_333_R_0002  rdf:type  cdm:resource_legal
res:oj/JOL_2022_333_R_0002  rdf:type  cdm:legislation_secondary
res:oj/JOL_2022_333_R_0002  rdf:type  cdm:directive          # the useful one: the document type
```

A resource carries its whole class chain; only the most specific class (`cdm:directive`) says something about the document.

### 4.3 Work attributes (literals)

On the OJ node of NIS2 (generic twins such as `cdm:date_document`, `cdm:identifier` exist as well):

```
res:oj/JOL_2022_333_R_0002  cdm:resource_legal_id_celex            "32022L2555"^^xsd:string
res:oj/JOL_2022_333_R_0002  cdm:resource_legal_type                "L"^^xsd:string
res:oj/JOL_2022_333_R_0002  cdm:resource_legal_year                "2022"^^xsd:gYear
res:oj/JOL_2022_333_R_0002  cdm:resource_legal_eli                 "http://data.europa.eu/eli/dir/2022/2555/oj"^^xsd:anyURI
res:oj/JOL_2022_333_R_0002  cdm:work_date_document                 "2022-12-14"^^xsd:date
res:oj/JOL_2022_333_R_0002  cdm:resource_legal_date_entry-into-force "2023-01-16"^^xsd:date
res:oj/JOL_2022_333_R_0002  cdm:resource_legal_date_deadline       "2028-01-16"^^xsd:date
res:celex/32022L2555        cdm:resource_legal_in-force            "true"^^xsd:boolean
```

Some values are placeholders: `cdm:date_end-of-validity "9999-12-31"` means "no end date". There is **no title** in the dumps
(titles are expression-level).

### 4.4 Outgoing relations between works

Stored on the OJ node, object is another work (usually in CELEX form):

```
res:oj/JOL_2022_333_R_0002  cdm:work_cites_work                      res:celex/32008R0300
res:oj/JOL_2022_333_R_0002  cdm:resource_legal_amends_resource_legal  res:celex/32018L1972
res:oj/JOL_2022_333_R_0002  cdm:resource_legal_repeals_resource_legal res:celex/32016L1148   # NIS2 repeals NIS1
```

### 4.5 Incoming relations (the bulk of every file)

Stored on the CELEX node – other documents pointing at the work. Together with the generic twins they make up the largest part of each dump.

```
res:celex/32022L2555  cdm:work_cited_by_work                                       res:comnat/SWD_2024_0699_FIN
res:celex/32022L2555  cdm:resource_legal_implemented_by_measure_national_implementing res:nim/202405193
res:celex/32022L2555  cdm:resource_legal_basis_for_resource_legal                   res:oj/L_202401101
res:celex/32022L2555  cdm:resource_legal_consolidated_by_act_consolidated           res:consolidation/2022L2555%2F20221227_0000090
res:celex/32022L2555  cdm:resource_legal_corrected_by_resource_legal                res:oj/L_202590309
```

The same relation can be stated from the other end in another file: the `amended_by` triple about eIDAS 1 above (see §4.8, found in the NIS2 file)
is the inverse of `res:oj/L_202401183 cdm:resource_legal_amends_resource_legal res:celex/32014R0910`, so loading several files without normalising
direction produces duplicates.

### 4.6 Links to reference data

```
res:oj/JOL_2022_333_R_0002  cdm:work_has_resource-type             res:authority/resource-type/DIR
res:oj/JOL_2022_333_R_0002  cdm:work_created_by_agent              res:authority/corporate-body/CONSIL
res:oj/JOL_2022_333_R_0002  cdm:resource_legal_is_about_subject-matter res:authority/subject-matter/TECN
res:oj/JOL_2022_333_R_0002  cdm:work_is_about_concept_eurovoc      http://eurovoc.europa.eu/c_57f3c49f
```

Reference-data nodes are described only by type and scheme; labels are not in the dumps:

```
res:authority/resource-type/DIR  rdf:type     cdm:resource-type
res:authority/resource-type/DIR  rdf:type     skos:Concept
res:authority/resource-type/DIR  skos:inScheme res:authority/resource-type
```

EuroVoc concepts appear mainly from the *inverse* side (concept → works):

```
http://eurovoc.europa.eu/4420  cdm:concept_eurovoc_subject_of_work  res:comnat/COM_2023_0668_FIN
http://eurovoc.europa.eu/4420  cdm:subject_of                       res:comnat/COM_2023_0668_FIN
```

### 4.7 Hierarchy links (not Work level) and lifecycle events

```
res:oj/JOL_2022_333_R_0002                         cdm:work_has_expression  res:oj/JOL_2022_333_R_0002.LIT
res:cellar/7e075fd8-34e9-11ed-9c68-01aa75ed71a1.0007  owl:sameAs            res:procedure-event/2022_272.2022-12-14_OPI_byEESC
```

The `….LIT` expression URIs carry nothing; manifestations and items do not occur in the dumps. The `cellar/<uuid>.NNNN` node is *not* an expression: it is
Cellar's id of an **event of a legislative procedure** (here an EESC opinion on 2022-12-14). Events, their dossiers and the links between them look like this
(the dossier/event nodes have no literals - date, code and body are only in the URI):

```
res:procedure/2020_359                                cdm:dossier_contains_event  res:procedure-event/2020_359.2022-12-27_PUB_OJ
res:celex/32022L2555                                  cdm:work_part_of_event      res:procedure-event/2020_359.2022-12-27_PUB_OJ   # NIS2 published
res:celex/32022L2555                                  cdm:resource_legal_produced_by_dossier  res:procedure/2020_359
res:comnat/COM_2020_0823_FIN                          cdm:initiates               res:procedure/2020_359                            # the proposal
res:authority/event/PUB_OJ                            cdm:is_type_of              res:procedure-event/2020_359.2022-12-27_PUB_OJ
```

The ETL pipeline keeps these with `--lifecycle` (see [ETL_PIPELINE.md §5](ETL_PIPELINE.md#5-document-lifecycle---lifecycle)).

### 4.8 Relation annotations – reification with `owl:Axiom`

A plain triple cannot carry details, so Cellar describes the *relation* with a blank node that points at its subject, property and object
(`rdf:Statement`-style) and adds `annot:` values. Real examples:

Amendment of eIDAS 1 by eIDAS 2 – which article, which role, from when:

```
_:A0  rdf:type                owl:Axiom
_:A0  owl:annotatedSource     res:celex/32014R0910
_:A0  owl:annotatedProperty   cdm:resource_legal_amended_by_resource_legal
_:A0  owl:annotatedTarget     res:oj/L_202401183
_:A0  annot:reference_to_modified_location "{AR|…/fd_370/AR} 32 {PA|…/fd_370/PA} 3"   # Article 32, paragraph 3
_:A0  annot:role2             "{R|…/fd_375/R}"
_:A0  annot:type_of_link_target "MS"
_:A0  annot:start_of_validity "2024-05-20"
```

Citation of the AI Act by a Court of Justice order – cited fragment:

```
_:b  owl:annotatedSource res:celex/32024R1689 ;  owl:annotatedProperty cdm:work_cited_by_work ;  owl:annotatedTarget res:celex/62024CO0806
_:b  annot:fragment_citing_source "N 5" ;  annot:fragment_cited_target "A95P2" ;  annot:build_info "reception-ID: …"
```

Transposition of NIS2 by a national measure:

```
_:b  owl:annotatedSource res:celex/32022L2555 ;  owl:annotatedProperty cdm:resource_legal_implemented_by_measure_national_implementing ;
     owl:annotatedTarget res:nim/202501642
_:b  annot:transposition_deadline_transmitted "2024-10-17" ;  annot:transposition_notification "2025-03-21"
```

Legal basis with article and comment:

```
_:b  owl:annotatedSource res:celex/32004D0002 ;  owl:annotatedProperty cdm:resource_legal_basis_for_resource_legal ;  owl:annotatedTarget res:oj/C_202602285
_:b  annot:article "17.5" ;  annot:comment_on_legal_basis "A17.5FR1"
```

Some values embed a code and its vocabulary URI as `{CODE|URI}` (`{R|…/fd_375/R}` = role code `R`).
Some axioms are **headless** – they lack `annotatedSource/Property/Target`, so they describe an amendment (`annot:reference_to_modified_location "ART:21 PAR:2"`,
`annot:impact "structure"`, `annot:start_of_validity "2018-12-11"`, …) without saying which relation it belongs to; they cannot be joined to an edge.

### 4.9 System metadata

```
res:cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1  cmr:creationDate          "2022-12-27T09:08:10.577000+01:00"^^xsd:dateTime
res:cellar/9b84d482-85bd-11ed-9887-01aa75ed71a1  cmr:lastModificationDate  "2024-01-21T01:38:57.400000+01:00"^^xsd:dateTime
res:oj/JOL_2022_333_R_0002  annot:build_info  "reception-ID: PO-20221227-44; environment: PROD; CERES: 4.17.2; IMMC2C"
```

Ingestion bookkeeping of the Cellar platform; no legal meaning.

## 5. Cheat sheet

| Pattern | Where | Example predicate | Work level? | Used in the knowledge graph |
|---|---|---|---|---|
| identity | Cellar node | `owl:sameAs` | yes (identifiers) | folded into identifiers of one node |
| document type | OJ/CELEX node | `rdf:type cdm:directive` | yes | `docType` |
| attributes | OJ node | `cdm:resource_legal_id_celex`, `cdm:work_date_document` | yes | node properties |
| outgoing relation | OJ node | `cdm:work_cites_work`, `…_amends_…` | yes | edge |
| incoming relation | CELEX node | `cdm:work_cited_by_work`, `…_implemented_by_…` | yes | edge (direction normalised) |
| reference-data link | OJ node / concept node | `cdm:work_is_about_concept_eurovoc`, `cdm:subject_of` | yes | edge to concept / institution |
| relation annotation | blank node | `owl:annotatedSource` + `annot:article` | yes | relationship properties |
| generic twin | same node as the specific one | `cdm:cited_by`, `cdm:date` | duplicate | dropped (fold) |
| expression link / `….LIT` node | OJ node | `cdm:work_has_expression` | no (Expression) | dropped |
| procedure event / dossier | `procedure-event/…`, `procedure/…`, Cellar `.NNNN` alias | `cdm:work_part_of_event`, `cdm:dossier_contains_event` | no (lifecycle) | `:Event` / `:Dossier` with `--lifecycle`, else dropped |
| language list | blank node | `annot:language_list` | no | dropped |
| system metadata | Cellar node / blank node | `cmr:*`, `annot:build_info` | no | optional / dropped |
