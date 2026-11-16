from enum import Enum

from rdflib import Namespace


########## WEMI HIERARCHY LEVELS ##########

class WEMILevel(Enum):
    """WEMI hierarchy levels for document loading."""
    WORK = "work"
    EXPRESSION = "expression"
    MANIFESTATION = "manifestation"
    ITEM = "item"

# All WEMI levels
ALL_WEMI_LEVELS = {WEMILevel.WORK, WEMILevel.EXPRESSION, WEMILevel.MANIFESTATION, WEMILevel.ITEM}

# Default WEMI levels to load (Work only)
DEFAULT_WEMI_LEVELS = {WEMILevel.WORK}


########## NEO4J DATABASE ##########

NEO4J_DEFAULT_HOST = "localhost"
NEO4J_DEFAULT_PORT = 7687
NEO4J_DEFAULT_USER = "neo4j"
NEO4J_DEFAULT_PASSWORD = "password"


########## TRANSFORMER ##########

TRANSFORM_LOGGER_NAME = "etlpipe.transform"


########## RDF NAMESPACES ##########

CDM_NS = Namespace("http://publications.europa.eu/ontology/cdm#")
CMR_NS = Namespace("http://publications.europa.eu/ontology/cdm/cmr#")
ANNOT_NS = Namespace("http://publications.europa.eu/ontology/annotation#")
SKOS_NS = Namespace("http://www.w3.org/2004/02/skos/core#")

RESOURCE_BASE = "http://publications.europa.eu/resource/"

# Output vocabulary of the transformer . Relation types are upper case local names (kms:CITES),
# node attributes are lower camel case (kms:dateEntryIntoForce).
KMS_NS = Namespace("https://management-system.local/kms#")

# node classes
KMS_WORK = KMS_NS.Work
KMS_CONCEPT = KMS_NS.Concept
KMS_INSTITUTION = KMS_NS.Institution
KMS_ENTITY = KMS_NS.Entity
KMS_DOSSIER = KMS_NS.Dossier
KMS_EVENT = KMS_NS.Event
NODE_CLASSES = (KMS_WORK, KMS_CONCEPT, KMS_INSTITUTION, KMS_DOSSIER, KMS_EVENT, KMS_ENTITY)

# node properties written by the pipeline itself
K_CELEX = KMS_NS.celex
K_CELLAR_ID = KMS_NS.cellarId
K_ELI = KMS_NS.eli
K_OJ_ID = KMS_NS.ojId
K_ALIAS = KMS_NS.alias
K_DOC_TYPE = KMS_NS.docType
K_STUB = KMS_NS.stub
K_SOURCE_KIND = KMS_NS.sourceKind
K_SCHEME = KMS_NS.scheme
K_CODE = KMS_NS.code
K_LOCATOR = KMS_NS.locator
