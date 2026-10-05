# Recursive Document Loader - Complete Guide

## Overview

The **RecursiveLoader** automatically fetches, parses, and loads documents recursively by following references. When a document references another legal act (via adoption, amendment, repeal, etc.), the loader can automatically fetch and load that referenced document, and continue recursively.

This enables building a comprehensive legal relationship graph without manually discovering and loading each document.

---

## Key Features

✅ **Automatic Reference Discovery** — Extracts referenced document URIs from relationships  
✅ **Recursive Loading** — Follows references up to a configurable depth  
✅ **Duplicate Prevention** — Tracks loaded documents to avoid reprocessing  
✅ **Error Handling** — Retries failed API calls with exponential backoff  
✅ **Rate Limiting** — Respects API rate limits with configurable delays  
✅ **Progress Tracking** — Optional callback for real-time progress updates  
✅ **Statistics Reporting** — Detailed metrics on fetch, parse, and load operations  
✅ **Thread-Safe** — Uses locks to prevent race conditions  

---

## Quick Start

### Installation

No additional dependencies needed beyond what's already required:
- `neo4j` (already installed)
- `requests` (used by Cellar client)

The recursive loader uses existing modules:
- `test.cellar.CellarClient` — API client
- `src.rdf_parser.RDFParser` — RDF/XML parser
- `src.neo4j_loader.Neo4jLoader` — Neo4j loader

### Basic Usage

```python
from neo4j import GraphDatabase
from test.cellar import CellarClient
from src.rdf_parser import RDFParser
from src.database_loader import Neo4jDatabaseLoader, RecursiveDocumentLoader

# 1. Initialize clients
cellar = CellarClient()
parser = RDFParser()
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
loader = Neo4jLoader(driver)
loader.create_constraints()

# 2. Create recursive loader with depth=2
recursive_loader = RecursiveLoader(
    cellar_client=cellar,
    rdf_parser=parser,
    neo4j_loader=loader,
    max_depth=2  # Load 2 levels deep
)

# 3. Load a document recursively
stats = recursive_loader.load_recursive(
    work_id='35e93bb4-8905-11e9-9369-01aa75ed71a1',  # ENISA Regulation
    include_references=True
)

print(f"Loaded {stats['documents_loaded']} documents")
driver.close()
```

---

## Parameters Explained

### RecursiveLoader Constructor

```python
RecursiveLoader(
    cellar_client,           # Cellar API client instance
    rdf_parser,              # RDF/XML parser instance
    neo4j_loader,            # Neo4j loader instance
    max_depth=2,             # Maximum recursion depth (0 = no recursion)
    retry_attempts=3,        # Retry failed API calls this many times
    rate_limit_delay=0.5     # Delay (seconds) between API calls
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cellar_client` | CellarClient | Required | API client for fetching metadata |
| `rdf_parser` | RDFParser | Required | Parser for RDF/XML responses |
| `neo4j_loader` | Neo4jLoader | Required | Loader for saving to Neo4j |
| `max_depth` | int | 2 | Maximum recursion depth. 0 = no recursion, 1 = load direct references only |
| `retry_attempts` | int | 3 | Number of retry attempts for failed API calls |
| `rate_limit_delay` | float | 0.5 | Seconds to wait between API calls (to respect rate limits) |

### load_recursive() Method

```python
stats = recursive_loader.load_recursive(
    work_id='35e93bb4-8905-11e9-9369-01aa75ed71a1',  # Required
    expr_id='0001',                                   # Optional
    man_id='01',                                      # Optional
    include_references=True,                          # Optional
    progress_callback=my_progress_handler             # Optional
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `work_id` | str | Required | UUID of the starting document |
| `expr_id` | str | '0001' | Expression ID (language version) |
| `man_id` | str | '01' | Manifestation ID (format) |
| `include_references` | bool | True | Whether to recursively load references |
| `progress_callback` | Callable | None | Callback function for progress updates |

**Return Value**:
```python
{
    'documents_fetched': 5,          # Number of API fetch operations
    'documents_parsed': 5,           # Number of successful parses
    'documents_loaded': 5,           # Number of successful Neo4j loads
    'references_discovered': 12,     # Total references found
    'fetch_errors': 0,               # Number of fetch failures
    'parse_errors': 0,               # Number of parse failures
    'load_errors': 0,                # Number of load failures
    'duplicates_skipped': 3,         # Documents already loaded
    'errors': [],                    # List of error messages
    'start_time': datetime,          # Start time
    'end_time': datetime             # End time
}
```

---

## Understanding Recursion Depth

### Depth = 0: No Recursion

```python
recursive_loader = RecursiveLoader(..., max_depth=0)
recursive_loader.load_recursive(work_id='...', include_references=True)
```

**Result**: Loads ONLY the starting document. References are NOT followed.

```
Document A
  └─ (references B, C, D - NOT loaded)
```

**Use case**: Load a single regulation without building a larger graph.

### Depth = 1: Direct References Only

```python
recursive_loader = RecursiveLoader(..., max_depth=1)
recursive_loader.load_recursive(work_id='...', include_references=True)
```

**Result**: Loads Document A and all documents it directly references (B, C, D).

```
                 ┌─→ B
                 ├─→ C
A (loaded)       └─→ D
  └─ references ↓
         (all loaded)
```

**Use case**: Load a regulation and all documents it immediately adopts/amends/repeals.

### Depth = 2: References of References

```python
recursive_loader = RecursiveLoader(..., max_depth=2)
recursive_loader.load_recursive(work_id='...', include_references=True)
```

**Result**: Loads A, all documents it references (B, C, D), and all documents that those reference (E, F, G, H, etc.).

```
                      ┌─→ E
           B (loaded)──┤─→ F
           ├─→ references ↓
A (loaded) ─┤
  └─ references ├─→ C (loaded)
           ├─→ G
           ├─→ H
           └─→ D (loaded)
                      └─→ I
```

**Use case**: Build a more comprehensive knowledge graph showing how regulations relate to each other across multiple generations.

---

## Progress Callback

Use the optional `progress_callback` parameter to receive real-time updates:

```python
def my_progress_handler(event_type: str, data: dict) -> None:
    """Handle progress events."""
    if event_type == 'fetch_start':
        print(f"Fetching: {data['work_id']}")
    elif event_type == 'load_success':
        print(f"Loaded: {data['work_id']}")
    elif event_type == 'complete':
        print(f"Done! Loaded {data['documents_loaded']} documents")

stats = recursive_loader.load_recursive(
    work_id='...',
    progress_callback=my_progress_handler
)
```

### Available Events

| Event | Data | Description |
|-------|------|-------------|
| `start` | `message`, `max_depth` | Loading started |
| `fetch_start` | `work_id`, `uri` | Starting API fetch |
| `fetch_success` | `work_id` | API fetch succeeded |
| `fetch_error` | `work_id`, `error` | API fetch failed |
| `parse_start` | `work_id` | Starting RDF parse |
| `parse_success` | `work_id`, `title` | RDF parse succeeded |
| `load_start` | `work_id` | Starting Neo4j load |
| `load_success` | `work_id` | Neo4j load succeeded |
| `load_error` | `work_id`, `error` | Neo4j load failed |
| `duplicate_skipped` | `uri` | Document already loaded |
| `no_references` | `document` | No references found |
| `depth_limit` | `depth`, `max_depth` | Max recursion depth reached |
| `complete` | (full stats dict) | Loading complete |

---

## Common Usage Patterns

### Pattern 1: Load Without Recursion (Single Document)

```python
recursive_loader = RecursiveLoader(..., max_depth=0)
stats = recursive_loader.load_recursive(
    work_id='35e93bb4-8905-11e9-9369-01aa75ed71a1',
    include_references=False  # Don't follow any references
)
```

**When to use**: Loading a specific regulation without discovering related documents.

### Pattern 2: Load with References

```python
recursive_loader = RecursiveLoader(..., max_depth=1)
stats = recursive_loader.load_recursive(
    work_id='35e93bb4-8905-11e9-9369-01aa75ed71a1',
    include_references=True  # Follow direct references only
)
```

**When to use**: Building a local knowledge graph of one regulation and its dependencies.

### Pattern 3: Deep Exploration

```python
recursive_loader = RecursiveLoader(..., max_depth=3)
stats = recursive_loader.load_recursive(
    work_id='35e93bb4-8905-11e9-9369-01aa75ed71a1',
    include_references=True
)
```

**When to use**: Deep exploration of regulation families and relationships.

### Pattern 4: Batch Load Multiple Documents

```python
documents = [
    '35e93bb4-8905-11e9-9369-01aa75ed71a1',  # ENISA
    'ANOTHER-UUID',                           # Other regulation
    # ... more UUIDs
]

loader = Neo4jLoader(driver)
loader.create_constraints()

for work_id in documents:
    recursive_loader = RecursiveLoader(
        cellar_client=cellar,
        rdf_parser=parser,
        neo4j_loader=loader,
        max_depth=1  # Shallow recursion
    )
    stats = recursive_loader.load_recursive(work_id)
    print(f"Loaded {stats['documents_loaded']} documents from {work_id}")
```

**When to use**: Loading multiple regulations and their immediate references.

### Pattern 5: With Error Handling

```python
try:
    stats = recursive_loader.load_recursive(work_id)
    
    if stats['errors']:
        print(f"⚠️  {len(stats['errors'])} errors encountered:")
        for error in stats['errors']:
            print(f"  - {error}")
    else:
        print("✅ All documents loaded successfully!")
        
except Exception as e:
    print(f"❌ Fatal error: {e}")
    # Handle recovery
```

---

## Performance Considerations

### API Rate Limiting

The loader respects Cellar API rate limits:

```python
recursive_loader = RecursiveLoader(
    ...,
    rate_limit_delay=0.5  # 500ms between requests
)
```

**Recommendation**: 
- Start with `rate_limit_delay=0.5` (500ms)
- Adjust based on API responses
- If you get rate limit errors, increase the delay

### Retry Logic

Failed API calls are automatically retried:

```python
recursive_loader = RecursiveLoader(
    ...,
    retry_attempts=3  # Try 3 times with exponential backoff
)
```

**Retry schedule**:
- Attempt 1: Immediate
- Attempt 2: After 1 second
- Attempt 3: After 2 seconds
- Failed: Skipped and logged

### Network Efficiency

The loader:
- ✅ Prevents duplicate fetches (tracks loaded URIs)
- ✅ Batches database operations (uses Neo4jLoader's batching)
- ✅ Closes connections properly
- ✅ Respects API rate limits

---

## Handling Errors

### Statistics

Always check the returned statistics:

```python
stats = recursive_loader.load_recursive(work_id)

print(f"Loaded: {stats['documents_loaded']}")
print(f"Errors: {len(stats['errors'])}")

if stats['fetch_errors'] > 0:
    print(f"⚠️  {stats['fetch_errors']} API calls failed")

if stats['load_errors'] > 0:
    print(f"⚠️  {stats['load_errors']} documents failed to load to Neo4j")
```

### Error Details

All errors are collected in `stats['errors']`:

```python
for error in stats['errors']:
    print(f"Error: {error}")

# Typical errors:
# - "Could not extract Cellar ID from reference: ..."
# - "Error loading 35e93bb4-...: Connection failed"
# - "Error loading 35e93bb4-...: Parse failed"
```

### Partial Success

The loader continues even if some documents fail:

```python
stats = recursive_loader.load_recursive(work_id)

# Typical scenario:
# - 5 documents fetched successfully
# - 1 document failed to parse (bad RDF)
# - 4 documents loaded to Neo4j
# - stats['documents_loaded'] = 4
# - stats['parse_errors'] = 1
# - stats['errors'] contains the details
```

---

## Querying Loaded Data

After loading documents recursively, query them in Neo4j:

### Find All Loaded Documents

```cypher
MATCH (d:Document)
RETURN d.title, d.cellar_id, d.created_date
ORDER BY d.created_date DESC
```

### Find Adoption Relationships

```cypher
MATCH (d1:Document)-[r:ADOPTS_REGULATION]->(d2:Document)
RETURN d1.title, d2.title, r.start_of_validity
```

### Find Relationship Chains

```cypher
MATCH path = (d1:Document)-[r:ADOPTS_REGULATION*1..2]->(d2:Document)
RETURN 
    d1.title as starting_document,
    LENGTH(path) as hops,
    d2.title as ending_document
```

### Find Most Referenced Documents

```cypher
MATCH ()-[r:ADOPTS_REGULATION|AMENDS_REGULATION]->(d:Document)
RETURN d.title, COUNT(r) as reference_count
ORDER BY reference_count DESC
```

---

## Running the Examples

A complete example script is provided: [test/example_recursive_load.py](test/example_recursive_load.py)

### Example 1: Simple Load (No Recursion)

```bash
python test/example_recursive_load.py
# Select: 1
```

Loads just the ENISA Regulation without following references.

### Example 2: Shallow Recursion

```bash
python test/example_recursive_load.py
# Select: 2
```

Loads ENISA and all documents it directly references.

### Example 3: Deeper Recursion

```bash
python test/example_recursive_load.py
# Select: 3
```

Loads ENISA, its references, and their references (2 levels deep).

### Example 4: Multiple Documents

```bash
python test/example_recursive_load.py
# Select: 4
```

Loads multiple documents with custom recursion depth for each.

### Example 5: Query Loaded Data

```bash
python test/example_recursive_load.py
# Select: 5
```

Runs various Cypher queries to explore the loaded data.

### Run All Examples

```bash
python test/example_recursive_load.py
# Select: all
```

Runs all examples sequentially.

---

## Troubleshooting

### "Connection refused" Error

**Problem**: Neo4j is not running or not accessible on the configured host.

**Solution**:
```bash
# Start Neo4j locally
docker run -p 7687:7687 -p 7474:7474 neo4j

# Or update connection string
driver = GraphDatabase.driver("bolt://your-host:7687", auth=("neo4j", "password"))
```

### "No documents parsed from RDF"

**Problem**: The Cellar API returned an empty or invalid response.

**Solution**:
- Verify the `work_id` is correct
- Check if the document still exists in Cellar
- The document might have restricted access

### "Max depth reached" Messages

**Problem**: Getting messages about recursion limit being reached.

**Solution**: This is normal behavior when many documents are referenced. Increase `max_depth` if you want deeper exploration.

### Slow Performance

**Problem**: Loading is taking a long time.

**Solutions**:
- Reduce `max_depth` (fewer documents to load)
- Increase `rate_limit_delay` if API is throttling
- Check network connectivity
- Verify Neo4j performance (check if it's indexing properly)

### Duplicate Warnings

**Problem**: Seeing many "Duplicate" messages.

**Solution**: This is normal. The loader prevents reprocessing the same document. The number should decrease as the loader progresses.

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                  RecursiveLoader                         │
│  ┌────────────────────────────────────────────────────┐  │
│  │  load_recursive(work_id, depth=2, callback)        │  │
│  │  ├─ _load_recursive_impl(depth=0)                  │  │
│  │  │  ├─ _load_single_document()                     │  │
│  │  │  │  ├─ _fetch_with_retry()  ────┐              │  │
│  │  │  │  ├─ parse()               ────┤─→ RDFParser │  │
│  │  │  │  └─ load_work()           ────┤─→ Neo4jLoader│  │
│  │  │  │                                 │              │  │
│  │  │  └─ _extract_reference_uris()     │              │  │
│  │  │     (find B, C, D in A's rels)   │              │  │
│  │  │     ├─ _extract_cellar_id()       │              │  │
│  │  │     └─ _load_recursive_impl(depth=1) (for B)    │  │
│  │  │        └─ ... (depth=1 finds E, F, G)           │  │
│  │  │           ├─ _load_recursive_impl(depth=2)      │  │
│  │  │           │  (depth limit reached, stop)        │  │
│  │  │           └─ ...                                 │  │
│  │  │                                                   │  │
│  │  └─ Duplicate tracking & error handling              │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘

Data Flow:
  API (Cellar)
       ↓
  RDFParser
       ↓
  Neo4jLoader
       ↓
  Neo4j Database
```

---

## Summary

The **RecursiveLoader** provides:

✅ Simple, one-line loading of documents and their references  
✅ Configurable depth to control graph size  
✅ Automatic duplicate prevention  
✅ Error handling and retry logic  
✅ Progress tracking and statistics  
✅ Thread-safe operation  

Perfect for building comprehensive legal relationship graphs without manual document discovery!
