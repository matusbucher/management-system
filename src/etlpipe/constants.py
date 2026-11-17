from enum import Enum

from rdflib import Namespace


########## WEMI HIERARCHY LEVELS ##########

class WEMILevel(Enum):
    """WEMI hierarchy levels for document loading."""
    WORK = "work"
    EXPRESSION = "expression"
    MANIFESTATION = "manifestation"
    ITEM = "item"

ALL_WEMI_LEVELS = frozenset({WEMILevel.WORK, WEMILevel.EXPRESSION, WEMILevel.MANIFESTATION, WEMILevel.ITEM})

DEFAULT_WEMI_LEVELS = frozenset({WEMILevel.WORK})


########## RDF NAMESPACES ##########

CDM = Namespace("http://publications.europa.eu/ontology/cdm#")
CMR = Namespace("http://publications.europa.eu/ontology/cdm/cmr#")
ANNOT = Namespace("http://publications.europa.eu/ontology/annotation#")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

RESOURCE_BASE = "http://publications.europa.eu/resource/"

# Output vocabulary of the transformer . Relation types are upper case local names (kms:CITES),
# node attributes are lower camel case (kms:dateEntryIntoForce).
KMS = Namespace("https://management-system.local/kms#")

# node classes
KMS_WORK = KMS.Work
KMS_CONCEPT = KMS.Concept
KMS_INSTITUTION = KMS.Institution
KMS_ENTITY = KMS.Entity
KMS_DOSSIER = KMS.Dossier
KMS_EVENT = KMS.Event
NODE_CLASSES = (KMS_WORK, KMS_CONCEPT, KMS_INSTITUTION, KMS_DOSSIER, KMS_EVENT, KMS_ENTITY)

# node properties written by the pipeline itself
K_CELEX = KMS.celex
K_CELLAR_ID = KMS.cellarId
K_ELI = KMS.eli
K_OJ_ID = KMS.ojId
K_ALIAS = KMS.alias
K_DOC_TYPE = KMS.docType
K_STUB = KMS.stub
K_SOURCE_KIND = KMS.sourceKind
K_SCHEME = KMS.scheme
K_CODE = KMS.code
K_LOCATOR = KMS.locator