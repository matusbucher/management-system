"""
Configuration of the document acquisition: which documents are the starting point, how the topic is defined and
which relations make documents "close" to each other. See docs/ACQUISITION_STRATEGY.md for the rationale.
"""
from __future__ import annotations

import re

from frozendict import frozendict


# Curated seed documents - the cybersecurity acts analysed in docs/RDF_METADATA_ANALYSIS.md (CELEX numbers).
SEED_CELEX = (
    "32013R0526",  # ENISA Regulation (repealed)
    "32014R0910",  # eIDAS 1
    "32016L1148",  # NIS 1 (repealed)
    "32016R0679",  # GDPR
    "32019R0881",  # Cybersecurity Act
    "32021R0887",  # European Cybersecurity Competence Centre
    "32022L2555",  # NIS 2
    "32022L2556",  # DORA amending directive
    "32022L2557",  # CER directive
    "32022R0868",  # Data Governance Act
    "32022R2554",  # DORA
    "32024R1183",  # eIDAS 2
    "32024R1689",  # AI Act
    "32024R2847",  # Cyber Resilience Act
)

# EuroVoc descriptors that define the topic (id -> English label). A work tagged with any of them is in the topic.
CORE_DESCRIPTORS = frozendict({
    "c_04ae3ba8": "information security",
    "3027": "computer crime",
    "17280": "cyber resilience",
    "c_57f3c49f": "critical infrastructure security",
    "7938": "European Union Agency for Cybersecurity",
    "c_439a1859": "information technology incident",
    "6779": "malware",
    "6778": "cryptography",
    "c_4e75f061": "information warfare",
    "8453": "digital evidence",
})

# Adjacent descriptors are too broad to define the topic alone (thousands of works); a work tagged with them is
# taken only if it is also directly linked to the documents already collected.
ADJACENT_DESCRIPTORS = frozendict({
    "6370": "electronic signature",
    "5181": "data protection",
    "2828": "protection of privacy",
    "5595": "personal data",
    "31800": "digital sovereignty",
})

EUROVOC_BASE = "http://eurovoc.europa.eu/"

# Legal relations (local names of CDM properties) between acts that are followed when expanding the collection.
# Both directions are used. National implementing measures (sector 7) are deliberately absent.
EXPANSION_RELATIONS = frozenset({
    "resource_legal_amends_resource_legal",
    "resource_legal_repeals_resource_legal",
    "resource_legal_based_on_resource_legal",
    "resource_legal_implements_resource_legal",
    "resource_legal_corrects_resource_legal",
    "resource_legal_adopts_resource_legal",
    "work_cites_work",
})

# Main legislative acts: CELEX sector 3 (acts of the institutions), without corrigenda, e.g. 32022L2555 but not 32022L2555R(01).
ACT_CELEX_PATTERN = re.compile(r"^3\d{4}[A-Z]\d{4}$")

# Types of acts (the letter after the year in the CELEX number) that are tagged with the topic descriptors but carry no
# legal content for the knowledge graph: B = budget and supplementary/amending budget (they mention every agency).
EXCLUDED_ACT_TYPES = frozenset({"B"})


def is_main_act(
    celex: str
) -> bool:
    """
    Decide whether a CELEX number identifies a main legislative act that belongs to the collection.

    Args:
        celex (str): The CELEX number.

    Returns:
        bool: True for a sector 3 act without corrigenda whose type is not excluded.
    """
    return bool(ACT_CELEX_PATTERN.match(celex)) and celex[5] not in EXCLUDED_ACT_TYPES

# The EUR-Lex expert query that restricts the web service search to legislation.
WEBSERVICE_SUBDOMAIN = "DTS_SUBDOM = LEGISLATION"
WEBSERVICE_PAGE_SIZE = 100
# The first year of EU legislation; used to slice large web service results by the year of the document date.
WEBSERVICE_FIRST_YEAR = 1957

DEFAULT_MIN_LINKS = 3
DEFAULT_ROUNDS = 1
