# CDM Ontology Overview (Version 4.17.0)

This folder contains the **Common Data Model (CDM)** formal ontology files downloaded from the [EU Publications Office EU Vocabularies dataset](https://op.europa.eu/en/web/eu-vocabularies/dataset/-/resource?uri=http://publications.europa.eu/resource/dataset/cdm). The CDM is the semantic backbone of the EU’s **CELLAR** repository, governing metadata representation for European legal, administrative, and general publications.

---

## Files Overview

The files are categorized below by their structural and modular roles:

### 1. Core Model & Extensions

* **`cdm.rdf`** – **The Core CDM Ontology.** Defines the primary classes (e.g., `cdm:regulation`, `cdm:case-law`, `cdm:directive`), object properties, and the foundational **WEMI (Work, Expression, Manifestation, Item)** bibliographic framework.
* **`cdmplus.rdf`** – **Supplemental CDM Properties.** Contains secondary extensions and auxiliary properties used alongside the core model.

### 2. Modular CDM Sub-Schemas

* **`cdm_cataloguing.rdf`** – Defines cataloguing rules and bibliographic metadata organization structures.
* **`cdm_annotationproperties.rdf`** – Contains specific metadata annotation properties used across EU documentation.
* **`cdm_datatypes.rdf`** – Enforces strict datatype constraints.
* **`cdm_indexation.rdf`** – Governs text indexation definitions and retrieval parameters.

### 3. External W3C & Standard Web Vocabularies

*(Included for offline resolution and semantic completeness)*

* **`skos.rdf`** / **`skos-xl.rdf`** – Simple Knowledge Organization System standards used for hierarchical thesauri and authority tables (like *EuroVoc*).
* **`rdfs.rdf`** / **`owl.rdf`** – Global W3C specifications for RDF Schema and Web Ontology Language constructs.
* **`dcat.rdf`** – Data Catalog Vocabulary for dataset descriptions.
* **`vcard.rdf`** – Standard contact information ontology.
* **`org.rdf`** – Organization ontology for modeling institutions, bodies, and departments.
* **`wgs84_pos.rdf`** – Spatial coordinates vocabulary.
* **`euvoc.rdf`** – EU Publications Office specific vocabulary definitions.

### 4. System & Tool Configuration (Safe to Ignore for Graph Imports)

* **`import.rdf`** – Internal Jena/Protégé system mapping policy.
* **`ont-policy.rdf`** – Redirection policy file for ontology development tools. *(Contains no graph data or triples).*
