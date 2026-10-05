# EU Cybersecurity Regulatory Documents - Database Schema

## Overview

This document describes the database schema for storing EU cybersecurity regulatory documents (NIS2, Cybersecurity Act, DORA, etc.). The database uses the **FRBR (Functional Requirements for Bibliographic Records)** model to represent documents at multiple hierarchical levels.

## Architecture

The schema implements a 4-level WEMI hierarchy:

```
Work (Legal Act)
  ├─ Expression (Language Version)
  │   ├─ Manifestation (Format/Medium)
  │   │   └─ Item (File Instance)
  │   └─ Manifestation (Another Format)
  │       └─ Item (File Instance)
  └─ Expression (Another Language)
      └─ Manifestation (Format)
          └─ Item (File Instance)
```

## Default Loading Behavior

By default, only the **Work level** is loaded into Neo4j to ensure:
- Efficient storage and querying
- Focus on regulatory requirements and legal relationships
- Simplified data model for compliance analysis

Optional: Can be configured to load Expression, Manifestation, and Item levels using the `wemi_levels` parameter in `Neo4jDatabaseLoader`.

---

## Neo4j Database Schema

The following tables describe the node types, properties, and relationships stored in Neo4j.

### Node Types

| Node Label | WEMI Level | Description |
|------------|-----------|-------------|
| `Document` | Work | A legal act or regulation (e.g., NIS2 Directive) |
| `DocumentVersion` | Expression | A language-specific version of a document |
| `DocumentFormat` | Manifestation | A format/medium version (PDF, XML, HTML, TXT) |
| `DocumentFile` | Item | An actual file instance with download URL |

---

## Node Properties

### Document (Work Level)

| Property | Type | Description |
|----------|------|-------------|
| `cellar_id` | String | Unique identifier in EUR-Lex Cellar |
| `cellar_uri` | String | Full URI in Cellar system (e.g., `http://data.europa.eu/eli/reg/2022/2554/oj`) |
| `created_date` | String | Date document was created (ISO 8601) |
| `modified_date` | String | Date document was last modified (ISO 8601) |
| `title` | String | Official title of the document |
| `document_type` | String | Type of legal act (Directive, Regulation, Decision, etc.) |

**Example Document:**
```
{
  "cellar_id": "32022R2554",
  "cellar_uri": "http://data.europa.eu/eli/reg/2022/2554/oj",
  "title": "Regulation (EU) 2022/2554 of the European Parliament and of the Council",
  "document_type": "Regulation",
  "created_date": "2022-12-16",
  "modified_date": "2023-01-15"
}
```

### DocumentVersion (Expression Level)

| Property | Type | Description |
|----------|------|-------------|
| `version_id` | String | Unique ID for this language version |
| `language` | String | Language code (e.g., "en", "fr", "de") |
| `language_iso_639_1` | String | ISO 639-1 code (2-letter language code) |
| `title` | String | Title in this language |
| `subtitle` | String | Subtitle in this language (optional) |
| `created_date` | String | Date version was created |
| `modified_date` | String | Date version was last modified |

**Properties:**
- Each Document can have multiple DocumentVersion nodes (one per language)
- Language field indicates which language this version represents
- Title may differ between language versions

### DocumentFormat (Manifestation Level)

| Property | Type | Description |
|----------|------|-------------|
| `format_id` | String | Unique ID for this format |
| `format_type` | String | Format type (PDF, XML, HTML, TXT, etc.) |
| `content_format` | String | MIME type or content format descriptor |
| `oj_volume` | Integer | Official Journal volume number (if applicable) |
| `oj_section` | String | Official Journal section (e.g., "L" for Legislation) |
| `oj_page_first` | Integer | First page in Official Journal |
| `oj_page_last` | Integer | Last page in Official Journal |
| `oj_natural_number` | String | Official Journal natural number |
| `created_date` | String | Date format was created |
| `modified_date` | String | Date format was last modified |

**Properties:**
- Each DocumentVersion can have multiple DocumentFormat nodes (one per format)
- Official Journal (OJ) properties track publication in the EU Official Journal
- Format field indicates the document format (PDF, XML, etc.)

### DocumentFile (Item Level)

| Property | Type | Description |
|----------|------|-------------|
| `file_id` | String | Unique identifier for the file |
| `mime_type` | String | MIME type (application/pdf, application/xml, text/html, etc.) |
| `url` | String | Download URL to the actual file |
| `created_date` | String | Date file was created/indexed |

**Properties:**
- Each DocumentFormat can have one or more DocumentFile nodes
- URL field points to the actual downloadable file
- MIME type indicates the file format

### Language Node

| Property | Type | Description |
|----------|------|-------------|
| `code_iso_639_3` | String | ISO 639-3 three-letter language code |
| `name` | String | Full language name (e.g., "English", "French") |

**Purpose:**
- Supports language filtering and multi-language querying
- Links to DocumentVersion nodes

---

## Relationships (Neo4j Edges)

Relationships connect nodes in the WEMI hierarchy and between Works.

### Hierarchy Relationships

| Relationship | Direction | Description |
|-------------|-----------|-------------|
| `HAS_VERSION` | Document → DocumentVersion | A document has language versions |
| `HAS_FORMAT` | DocumentVersion → DocumentFormat | A version has format variants |
| `HAS_FILE` | DocumentFormat → DocumentFile | A format has file instances |

**Example hierarchy:**
```
Document (NIS2)
  ├─ HAS_VERSION → DocumentVersion (EN)
  │    ├─ HAS_FORMAT → DocumentFormat (PDF)
  │    │    └─ HAS_FILE → DocumentFile (PDF URL)
  │    └─ HAS_FORMAT → DocumentFormat (XML)
  │         └─ HAS_FILE → DocumentFile (XML URL)
  └─ HAS_VERSION → DocumentVersion (FR)
       └─ HAS_FORMAT → DocumentFormat (PDF)
            └─ HAS_FILE → DocumentFile (PDF URL)
```

### Document Relationship Types

Between Work-level documents:

| Relationship | Description |
|-------------|-------------|
| `REPEALS` | This document repeals another document |
| `AMENDED_BY` | This document is amended by another |
| `AMENDS` | This document amends another document |
| `IMPLEMENTS` | This document implements an international agreement |
| `IMPLEMENTED_BY` | This document is implemented by national law |
| `SUPPLEMENTS` | This document supplements another document |
| `SUPPLEMENTED_BY` | This document is supplemented by another |
| `RELATED` | General relationship to another document |
| `MODIFIED_BY` | This document is modified by another |
| `MODIFIES` | This document modifies another document |

**Examples:**
- Directive 2022/2555 (NIS2) `AMENDED_BY` Regulation 2023/123
- Regulation 2022/2554 (DORA) `RELATED` Directive 2022/2555 (NIS2)
- Directive 2014/910 (eIDAS) `AMENDED_BY` Regulation 2024/1183 (eIDAS 2.0)

---

## Data Model Details

### Work (Document)

**From RDF Parser (src/rdf_parser.py):**
```python
@dataclass
class Work:
    uri: str                          # Cellar URI
    work_id: str                      # Unique work identifier
    title: Optional[str]
    subtitle: Optional[str]
    creation_date: Optional[str]      # ISO 8601
    last_modification_date: Optional[str]
    expressions: List[Expression]     # Language versions
    relationships: Dict[str, Any]     # Links to other Works
    same_as: List[str]                # Alternative URIs
    properties: Dict[str, Any]        # Additional RDF properties
```

### Expression (Language Version)

**From RDF Parser:**
```python
@dataclass
class Expression:
    uri: str
    language_code: Optional[str]      # e.g., "en", "fr"
    language_iso: Optional[str]       # e.g., "EN", "FR"
    title: Optional[str]
    subtitle: Optional[str]
    belongs_to_work: Optional[str]    # Reference to parent Work
    uses_language: Optional[str]      # Language URI
    creation_date: Optional[str]
    last_modification_date: Optional[str]
    manifestations: List[Manifestation]
    same_as: List[str]
    properties: Dict[str, Any]
```

### Manifestation (Format/Medium)

**From RDF Parser:**
```python
@dataclass
class Manifestation:
    uri: str
    type: Optional[str]               # Format type (e.g., "PDF", "XML")
    language_code: Optional[str]
    manifests_expression: Optional[str]  # Reference to parent Expression
    part_of_manifestation: Optional[str] # For composite documents
    creation_date: Optional[str]
    last_modification_date: Optional[str]
    items: List[Item]                 # File instances
    same_as: List[str]
    properties: Dict[str, Any]
```

### Item (File)

**From RDF Parser:**
```python
@dataclass
class Item:
    uri: str
    identifier: Optional[str]
    mime_type: Optional[str]          # e.g., "application/pdf"
    belongs_to_manifestation: Optional[str]  # Reference to parent
    same_as: List[str]
```

---

## Sample Query Examples

### Query 1: Find all versions of NIS2 Directive
```cypher
MATCH (doc:Document)-[r:HAS_VERSION]->(v:DocumentVersion)
WHERE doc.title CONTAINS "NIS2"
RETURN doc.title, v.language, v.version_id
```

### Query 2: Find documents that NIS2 relates to
```cypher
MATCH (nis2:Document)-[rel]->(other:Document)
WHERE nis2.title CONTAINS "NIS2"
RETURN rel, other.title, type(rel)
```

### Query 3: Get PDF download link for DORA in English
```cypher
MATCH (doc:Document)-[:HAS_VERSION]->(v:DocumentVersion)-[:HAS_FORMAT]->(f:DocumentFormat)-[:HAS_FILE]->(file:DocumentFile)
WHERE doc.title CONTAINS "DORA" 
  AND v.language = "en"
  AND f.format_type = "PDF"
RETURN file.url
```

### Query 4: Find all documents related to cybersecurity (by content search)
```cypher
MATCH (doc:Document)
WHERE doc.title CONTAINS "cyber" OR doc.title CONTAINS "security"
RETURN doc.title, doc.cellar_uri, doc.created_date
```

### Query 5: Build regulatory dependency chain
```cypher
MATCH path = (nist:Document)-[rel*1..3]->(related:Document)
WHERE nist.title CONTAINS "NIS2"
RETURN path, [r in relationships(path) | type(r)]
```

---

## Data Loading Process

The ETL pipeline in [test/test_etl.py](../test/test_etl.py) implements a 4-stage process:

### Stage 1: Search
- **Input:** CELEX identifier (e.g., "32022L2555")
- **Process:** Query EUR-Lex SOAP webservice
- **Output:** Work UUID
- **Retry Logic:** 3 attempts with exponential backoff

### Stage 2: Extract
- **Input:** Work UUID
- **Process:** Fetch RDF/XML metadata from Cellar API
- **Output:** RDF/XML bytes
- **Rate Limiting:** 0.5 seconds between calls

### Stage 3: Parse
- **Input:** RDF/XML bytes
- **Process:** Convert to Work/Expression/Manifestation/Item objects
- **Output:** Python dataclass instances
- **Error Handling:** Validation and schema compliance checks

### Stage 4: Load
- **Input:** Work object
- **Process:** Create Neo4j nodes and relationships
- **Output:** Database nodes
- **Filtering:** By default, only loads Work level (configurable)

---

## Key Characteristics

### Multilingual Support
- Each document can have expressions (versions) in multiple languages
- Language-specific querying and filtering
- Metadata (title, etc.) per language

### Multiple Format Support
- Single document can be available in multiple formats (PDF, XML, HTML, TXT)
- Download URLs point to actual files
- Format-specific metadata (Official Journal references)

### Relationship Tracking
- Legal relationships between documents (amendments, implementations, etc.)
- Transitive relationships enable compliance chain analysis
- Bidirectional relationships (e.g., "AMENDED_BY" / "AMENDS")

### Official Journal Tracking
- Publication metadata for Official Journal publications
- Volume, section, page ranges
- Supports regulatory publication history

### Audit Trail
- Creation and modification dates at each level
- Enables tracking of document evolution
- Version history management

---

## Configuration Parameters

### Neo4j Connection
```python
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
```

### ETL Pipeline Settings
```python
MAX_RECURSION_DEPTH = 1           # Load only Work + direct Expressions
RATE_LIMIT_DELAY = 0.5            # Delay between API calls (seconds)
RETRY_ATTEMPTS = 3                # Number of retries on failure
```

### WEMI Level Filtering
```python
# Default: Work level only
wemi_levels = {WEMILevel.WORK}

# To load all levels:
wemi_levels = {
    WEMILevel.WORK,
    WEMILevel.EXPRESSION,
    WEMILevel.MANIFESTATION,
    WEMILevel.ITEM
}

# Custom combinations supported:
wemi_levels = {WEMILevel.WORK, WEMILevel.EXPRESSION}
```

---

## Performance Considerations

1. **Default Work-Level Loading:** Optimized for legal analysis with minimal storage overhead
2. **Lazy Loading:** Expression/Manifestation/Item levels can be added on-demand
3. **Indexing:** CELLAR_ID and TITLE fields should be indexed for query performance
4. **Relationship Caching:** Frequently accessed relationship types should be pre-computed
5. **Pagination:** Large result sets should use LIMIT/SKIP for query efficiency

---

## Future Extensions

1. **Full-Text Search:** Add Lucene indices for document content search
2. **Temporal Queries:** Track document evolution over time
3. **Compliance Mapping:** Map regulatory requirements to technical controls
4. **Amendment Tracking:** Build amendment chains and compliance status
5. **Cross-Reference Analysis:** Track how documents reference each other
6. **Integration with External Databases:** Link to national law implementations

---

## Documents Included

| Document | CELEX | Type | Description |
|----------|-------|------|-------------|
| NIS2 Directive | 32022L2555 | Directive | Network and Information Security Directive |
| Cybersecurity Act | 32019R0881 | Regulation | EU Cybersecurity Act 2019 |
| DORA | 32022R2554 | Regulation | Digital Operational Resilience Act |
| CER Directive | 32022L2557 | Directive | Critical Entities Resilience Directive |
| Cyber Resilience Act | 32024R2847 | Regulation | Cyber Resilience Act 2024 |
| eIDAS 2.0 Part 1 | 32014R0910 | Regulation | Electronic Identification & Trust Services |
| eIDAS 2.0 Part 2 | 32024R1183 | Regulation | eIDAS amendments 2024 |

---

## Related Files

- **ETL Pipeline:** [test/cybersecurity_etl_pipeline.py](../test/cybersecurity_etl_pipeline.py)
- **RDF Parser:** [src/rdf_parser.py](../src/rdf_parser.py)
- **Database Loader:** [src/database_loader.py](../src/database_loader.py)
- **Constants & Schema Definitions:** [src/constants.py](../src/constants.py)
- **Cellar API Client:** [src/cellar.py](../src/cellar.py)
- **EUR-Lex Webservice:** [src/webservice.py](../src/webservice.py)
