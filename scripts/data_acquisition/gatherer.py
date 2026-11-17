from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Iterator, Optional
from urllib.request import urlopen

from src.eurlex.cellar_api import CellarAPI, CellarPS, CellarResourceId
from src.eurlex.sparql_api import SparqlAPI
from src.eurlex.webservice_api import WebserviceAPI
from .config import (ADJACENT_DESCRIPTORS, CORE_DESCRIPTORS, DEFAULT_MIN_LINKS, DEFAULT_ROUNDS, EUROVOC_BASE,
                     EXPANSION_RELATIONS, SEED_CELEX, WEBSERVICE_FIRST_YEAR, WEBSERVICE_PAGE_SIZE, WEBSERVICE_SUBDOMAIN, is_main_act)

_LOGGER_NAME = "acquisition"

logger = logging.getLogger(_LOGGER_NAME)

_CELLAR_WORK_URI = "http://publications.europa.eu/resource/cellar/"
_CDM = "http://publications.europa.eu/ontology/cdm#"
_SPARQL_PREFIX = f"PREFIX cdm: <{_CDM}>\nPREFIX r: <{_CELLAR_WORK_URI}>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
_WEBSERVICE_REFERENCE = re.compile(r"cellar:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")

# The SPARQL endpoint rejects (HTTP 403) requests larger than about 6 KB, so the collected works are sent in chunks
# of this many IDs (about 40 characters each with the ``r:`` prefix) and the partial results are merged here.
_CHUNK_SIZE = 50

STAGE_SEED = "seed"
STAGE_TOPIC = "topic"
STAGE_EXPANSION = "expansion"

SOURCE_CELLAR = "cellar"
SOURCE_SPARQL = "sparql"
SOURCE_WEBSERVICE = "webservice"


@dataclass
class GatheredWork:
    """
    One collected work and how it got into the collection.

    Attributes:
        work_id (str): Cellar work UUID.
        celex (Optional[str]): CELEX number of the work, if known.
        stages (set[str]): Stages that selected the work (``seed``, ``topic``, ``expansion``).
        sources (set[str]): Services that reported the work (``cellar``, ``sparql``, ``webservice``).
        links (int): For works selected by the expansion: number of collected works they are linked to.
    """
    work_id: str
    celex: Optional[str] = None
    stages: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    links: int = 0


@dataclass
class GatherResult:
    """
    Outcome of the acquisition.

    Attributes:
        works (dict[str, GatheredWork]): The collected works by work ID.
        stats (dict[str, Any]): Counters and coherence metrics of the run (JSON serialisable).
    """
    works: dict[str, GatheredWork] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)


class WorkIdGatherer:
    """
    Gathers the Cellar work IDs of the documents to load into the knowledge graph.

    The collection is built in three stages (see docs/ACQUISITION_STRATEGY.md): the curated seeds, the documents about
    the topic (EuroVoc descriptors) and the documents closely linked to what has been collected so far. Only IDs are
    collected - no document metadata is downloaded.

    Args:
        sparql (Optional[SparqlAPI]): SPARQL endpoint wrapper. Default ``SparqlAPI()``.
        webservice (Optional[WebserviceAPI]): EUR-Lex web service wrapper used to cross-check the topic search. If None,
            the web service is not used. Default None.
        delay (float): Pause in seconds between calls to the Cellar API and the web service. Default 1.0.
    """

    def __init__(
        self,
        sparql: Optional[SparqlAPI] = None,
        webservice: Optional[WebserviceAPI] = None,
        delay: float = 1.0
    ) -> None:
        self.sparql = sparql or SparqlAPI()
        self.webservice = webservice
        self.delay = delay

    # ---- stage 1: seeds ----------------------------------------------------------------------------------------------
    def resolve_celex(
        self,
        celex_numbers: Iterable[str]
    ) -> dict[str, str]:
        """
        Resolve CELEX numbers to Cellar work IDs with the identifiers notice of the Cellar API.

        A CELEX number the Cellar API cannot resolve is looked up in the SPARQL endpoint instead.

        Args:
            celex_numbers (Iterable[str]): The CELEX numbers to resolve.

        Returns:
            dict[str, str]: Work ID by CELEX number; unresolved numbers are missing.
        """
        resolved: dict[str, str] = {}
        unresolved: list[str] = []
        for celex in celex_numbers:
            try:
                request = CellarAPI.indentifiers_notice_request(CellarResourceId(CellarPS.CELEX, celex))
                with urlopen(request, timeout=60) as response:
                    work_id = CellarAPI.extract_identifiers(response.read().decode("utf-8")).get(CellarPS.CELLAR.value)
            except Exception as exc:
                logger.warning("cellar: cannot resolve %s: %s", celex, exc)
                work_id = None
            if work_id:
                resolved[celex] = work_id
            else:
                unresolved.append(celex)
            time.sleep(self.delay)
        if unresolved:
            for work_id, celex in self.celex_lookup(unresolved).items():
                resolved[celex] = work_id
        return resolved

    def celex_lookup(
        self,
        celex_numbers: list[str]
    ) -> dict[str, str]:
        """
        Look up the work IDs of CELEX numbers in the SPARQL endpoint.

        Args:
            celex_numbers (list[str]): The CELEX numbers to look up.

        Returns:
            dict[str, str]: CELEX number by work ID.
        """
        found: dict[str, str] = {}
        for chunk in _chunks(celex_numbers, _CHUNK_SIZE):
            values = " ".join(f'"{celex}"^^xsd:string' for celex in chunk)
            query = _SPARQL_PREFIX + f"SELECT ?w ?celex WHERE {{ VALUES ?celex {{ {values} }} ?w cdm:resource_legal_id_celex ?celex }}"
            for row in self.sparql.select(query):
                found[_work_id(row["w"])] = row["celex"]
        return found

    # ---- stage 2: topic ----------------------------------------------------------------------------------------------
    def topic_sparql(
        self,
        descriptors: Iterable[str]
    ) -> dict[str, str]:
        """
        Find the acts tagged with any of the EuroVoc descriptors using the SPARQL endpoint.

        Args:
            descriptors (Iterable[str]): EuroVoc concept IDs (e.g. ``c_04ae3ba8`` or ``3027``).

        Returns:
            dict[str, str]: CELEX number by work ID of the main acts (corrigenda, budget acts and non-legislation excluded).
        """
        values = _values(f"{EUROVOC_BASE}{descriptor}" for descriptor in descriptors)
        query = _SPARQL_PREFIX + (
            f"SELECT DISTINCT ?w ?celex WHERE {{ VALUES ?c {{ {values} }} "
            f"?w cdm:work_is_about_concept_eurovoc ?c ; cdm:resource_legal_id_celex ?celex . "
            f'FILTER(STRSTARTS(STR(?celex), "3")) }}'
        )
        return {_work_id(row["w"]): row["celex"] for row in self.sparql.select(query) if is_main_act(row["celex"])}

    def topic_webservice(
        self,
        descriptors: Iterable[str]
    ) -> set[str]:
        """
        Find the legislation tagged with any of the EuroVoc descriptors using the EUR-Lex web service.

        The web service returns at most 100 results per page and the order of the results is not stable, so paging
        through a large result silently skips and repeats documents. When a descriptor has more than one page of
        results, it is therefore queried again once per year of the document date, which keeps every query small.

        Args:
            descriptors (Iterable[str]): EuroVoc concept IDs.

        Returns:
            set[str]: Work IDs of the results; they still have to be checked for being main acts.

        Raises:
            RuntimeError: If the web service wrapper was not provided.
        """
        if self.webservice is None:
            raise RuntimeError("The web service wrapper was not provided")
        work_ids: set[str] = set()
        for descriptor in descriptors:
            query = f"DC_CODED = {descriptor} AND {WEBSERVICE_SUBDOMAIN}"
            first_page = self._search(query, 1)
            if len(first_page) < WEBSERVICE_PAGE_SIZE:
                work_ids.update(_work_ids_of(first_page))
                continue
            for year in range(WEBSERVICE_FIRST_YEAR, date.today().year + 1):
                page = 1
                while True:
                    references = self._search(f"{query} AND DD_YEAR = {year}", page)
                    work_ids.update(_work_ids_of(references))
                    if len(references) < WEBSERVICE_PAGE_SIZE:
                        break
                    logger.warning("web service: descriptor %s has more than a page of results in %d, paging is unstable", descriptor, year)
                    page += 1
        return work_ids

    def _search(
        self,
        query: str,
        page: int
    ) -> list[str]:
        """
        Run one expert query on the web service and pause afterwards to respect its rate limit.

        Args:
            query (str): The expert query.
            page (int): The page of the results.

        Returns:
            list[str]: The references of the results on the page.
        """
        assert self.webservice is not None
        references = self.webservice.search(query, page=page, page_size=WEBSERVICE_PAGE_SIZE)
        time.sleep(self.delay)
        return references

    def celex_of(
        self,
        work_ids: Iterable[str]
    ) -> dict[str, str]:
        """
        Find the CELEX numbers of works; only works that are main acts are returned.

        Args:
            work_ids (Iterable[str]): The work IDs.

        Returns:
            dict[str, str]: CELEX number by work ID of the main acts among the given works.
        """
        found: dict[str, str] = {}
        for chunk in _chunks(sorted(work_ids), _CHUNK_SIZE):
            query = _SPARQL_PREFIX + f"SELECT DISTINCT ?w ?celex WHERE {{ VALUES ?w {{ {_work_values(chunk)} }} ?w cdm:resource_legal_id_celex ?celex }}"
            for row in self.sparql.select(query):
                if is_main_act(row["celex"]):
                    found[_work_id(row["w"])] = row["celex"]
        return found

    # ---- stage 3: expansion ------------------------------------------------------------------------------------------
    def expand(
        self,
        collected: Iterable[str],
        min_links: int,
        adjacent_descriptors: Iterable[str]
    ) -> dict[str, tuple[str, int]]:
        """
        Find acts closely linked to the collected works.

        An act qualifies if it is linked (in either direction, by any expansion relation) to at least ``min_links``
        collected works, or if it is linked to at least one and is tagged with an adjacent descriptor.

        Args:
            collected (Iterable[str]): Work IDs collected so far.
            min_links (int): Minimum number of collected works an act has to be linked to.
            adjacent_descriptors (Iterable[str]): EuroVoc IDs that lower the requirement to a single link.

        Returns:
            dict[str, tuple[str, int]]: (CELEX number, number of links) by work ID of the qualifying acts that are not
                collected yet.
        """
        members = set(collected)
        neighbours: dict[str, set[str]] = {}
        for chunk in _chunks(sorted(members), _CHUNK_SIZE):
            values = _work_values(chunk)
            for relation in sorted(EXPANSION_RELATIONS):
                # one simple query per relation and direction: joins with the CELEX numbers in the same query are very slow
                for pattern in (f"?m cdm:{relation} ?n", f"?n cdm:{relation} ?m"):
                    query = _SPARQL_PREFIX + f"SELECT DISTINCT ?m ?n WHERE {{ VALUES ?m {{ {values} }} {pattern} }}"
                    for row in self.sparql.select(query):
                        work_id = _work_id(row["n"])
                        if work_id not in members:
                            neighbours.setdefault(work_id, set()).add(_work_id(row["m"]))
        logger.info("expansion: %d works are linked to the %d collected works", len(neighbours), len(members))

        acts = self.act_info(neighbours.keys(), adjacent_descriptors)
        return {
            work_id: (celex, len(neighbours[work_id]))
            for work_id, (celex, tagged) in acts.items()
            if len(neighbours[work_id]) >= min_links or tagged
        }

    def act_info(
        self,
        work_ids: Iterable[str],
        descriptors: Iterable[str]
    ) -> dict[str, tuple[str, bool]]:
        """
        Find the CELEX numbers of works and whether they are tagged with any of the descriptors; only main acts are returned.

        Args:
            work_ids (Iterable[str]): The work IDs.
            descriptors (Iterable[str]): EuroVoc IDs to check.

        Returns:
            dict[str, tuple[str, bool]]: (CELEX number, tagged) by work ID of the main acts among the given works.
        """
        tags = _values(f"{EUROVOC_BASE}{descriptor}" for descriptor in descriptors)
        found: dict[str, tuple[str, bool]] = {}
        for chunk in _chunks(sorted(work_ids), _CHUNK_SIZE):
            query = _SPARQL_PREFIX + (
                f"SELECT ?w (SAMPLE(?number) AS ?celex) (COUNT(DISTINCT ?c) AS ?tags) WHERE {{ VALUES ?w {{ {_work_values(chunk)} }} "
                f"?w cdm:resource_legal_id_celex ?number . "
                f"OPTIONAL {{ ?w cdm:work_is_about_concept_eurovoc ?c . VALUES ?c {{ {tags} }} }} }} GROUP BY ?w"
            )
            for row in self.sparql.select(query):
                if is_main_act(row["celex"]):
                    found[_work_id(row["w"])] = (row["celex"], int(row["tags"]) > 0)
        return found

    # ---- coherence ---------------------------------------------------------------------------------------------------
    def coherence(
        self,
        work_ids: Iterable[str]
    ) -> dict[str, Any]:
        """
        Measure how well the collected works are connected to each other by the expansion relations.

        Args:
            work_ids (Iterable[str]): The collected work IDs.

        Returns:
            dict[str, Any]: ``edges`` (number of distinct links inside the collection), ``edges_by_relation``,
                ``linked_works`` (works with at least one link inside the collection), ``isolated`` (work IDs without any).
        """
        ids = sorted(work_ids)
        members = set(ids)
        properties = ", ".join(f"cdm:{name}" for name in sorted(EXPANSION_RELATIONS))
        edges: set[tuple[str, str, str]] = set()
        for chunk in _chunks(ids, _CHUNK_SIZE):
            query = _SPARQL_PREFIX + (
                f"SELECT DISTINCT ?a ?p ?b WHERE {{ VALUES ?a {{ {_work_values(chunk)} }} ?a ?p ?b . "
                f"FILTER(?a != ?b && ?p IN ({properties})) }}"
            )
            edges.update(
                (_work_id(row["a"]), row["p"].removeprefix(_CDM), _work_id(row["b"]))
                for row in self.sparql.select(query) if _work_id(row["b"]) in members
            )
        by_relation: dict[str, int] = {}
        linked: set[str] = set()
        for source, relation, target in edges:
            by_relation[relation] = by_relation.get(relation, 0) + 1
            linked.update((source, target))
        return {
            "edges": len(edges),
            "edges_by_relation": dict(sorted(by_relation.items(), key=lambda item: -item[1])),
            "linked_works": len(linked),
            "isolated": sorted(members - linked),
        }

    # ---- orchestration -----------------------------------------------------------------------------------------------
    def gather(
        self,
        seed_celex: Iterable[str] = SEED_CELEX,
        core_descriptors: Iterable[str] = CORE_DESCRIPTORS,
        adjacent_descriptors: Iterable[str] = ADJACENT_DESCRIPTORS,
        min_links: int = DEFAULT_MIN_LINKS,
        rounds: int = DEFAULT_ROUNDS
    ) -> GatherResult:
        """
        Run the acquisition and return the collected works.

        Args:
            seed_celex (Iterable[str]): CELEX numbers of the curated seeds. Default ``SEED_CELEX``.
            core_descriptors (Iterable[str]): EuroVoc IDs that define the topic. Default ``CORE_DESCRIPTORS``.
            adjacent_descriptors (Iterable[str]): EuroVoc IDs of adjacent topics. Default ``ADJACENT_DESCRIPTORS``.
            min_links (int): Minimum number of collected works an expanded act has to be linked to. Default 3.
            rounds (int): Number of expansion rounds; 0 disables the expansion. Default 1.

        Returns:
            GatherResult: The collected works with provenance, and the statistics of the run.
        """
        result = GatherResult()
        works = result.works
        stats = result.stats

        def add(
            work_id: str,
            celex: Optional[str],
            stage: str,
            source: str,
            links: int = 0
        ) -> None:
            work = works.setdefault(work_id, GatheredWork(work_id))
            work.celex = work.celex or celex
            work.stages.add(stage)
            work.sources.add(source)
            work.links = max(work.links, links)

        seeds = list(seed_celex)
        resolved = self.resolve_celex(seeds)
        for celex, work_id in resolved.items():
            add(work_id, celex, STAGE_SEED, SOURCE_CELLAR)
        stats["seeds"] = {"requested": len(seeds), "resolved": len(resolved), "unresolved": sorted(set(seeds) - set(resolved))}
        logger.info("seeds: %d of %d CELEX numbers resolved", len(resolved), len(seeds))

        core = list(core_descriptors)
        from_sparql = self.topic_sparql(core)
        for work_id, celex in from_sparql.items():
            add(work_id, celex, STAGE_TOPIC, SOURCE_SPARQL)
        topic_stats: dict[str, Any] = {"descriptors": len(core), "sparql": len(from_sparql)}
        if self.webservice is not None:
            from_webservice = self.celex_of(self.topic_webservice(core))
            for work_id, celex in from_webservice.items():
                add(work_id, celex, STAGE_TOPIC, SOURCE_WEBSERVICE)
            topic_stats.update(
                webservice=len(from_webservice),
                both=len(from_sparql.keys() & from_webservice.keys()),
                sparql_only=len(from_sparql.keys() - from_webservice.keys()),
                webservice_only=len(from_webservice.keys() - from_sparql.keys()),
            )
        stats["topic"] = topic_stats
        logger.info("topic: %s", topic_stats)

        adjacent = list(adjacent_descriptors)
        stats["expansion"] = []
        for round_number in range(1, rounds + 1):
            found = self.expand(works.keys(), min_links, adjacent)
            for work_id, (celex, links) in found.items():
                add(work_id, celex, STAGE_EXPANSION, SOURCE_SPARQL, links)
            stats["expansion"].append({"round": round_number, "added": len(found)})
            logger.info("expansion round %d: %d works added", round_number, len(found))
            if not found:
                break

        for work in works.values():
            if work.celex is None:
                logger.warning("work %s has no CELEX number", work.work_id)
        stats["works"] = len(works)
        stats["by_stage"] = {stage: sum(stage in work.stages for work in works.values()) for stage in (STAGE_SEED, STAGE_TOPIC, STAGE_EXPANSION)}
        stats["coherence"] = self.coherence(works.keys())
        logger.info("coherence: %d works, %d links inside, %d isolated", len(works), stats["coherence"]["edges"], len(stats["coherence"]["isolated"]))
        return result


def _work_ids_of(
    references: Iterable[str]
) -> set[str]:
    """
    Get the work UUIDs from web service references such as ``eng_cellar:<uuid>_en``.

    Args:
        references (Iterable[str]): The references returned by the web service.

    Returns:
        set[str]: The work UUIDs of the references that contain one.
    """
    return {match.group(1) for reference in references if (match := _WEBSERVICE_REFERENCE.search(reference))}


def _work_id(
    uri: str
) -> str:
    """
    Get the work UUID from a Cellar work URI.

    Args:
        uri (str): The Cellar work URI.

    Returns:
        str: The last path segment of the URI.
    """
    return uri.rsplit("/", 1)[-1]


def _values(
    uris: Iterable[str]
) -> str:
    """
    Format URIs as the content of a SPARQL ``VALUES`` block.

    Args:
        uris (Iterable[str]): The URIs.

    Returns:
        str: The URIs in angle brackets separated by spaces.
    """
    return " ".join(f"<{uri}>" for uri in uris)


def _work_values(
    work_ids: Iterable[str]
) -> str:
    """
    Format work IDs as the content of a SPARQL ``VALUES`` block, using the ``r:`` prefix to keep the query short.

    Args:
        work_ids (Iterable[str]): The work IDs.

    Returns:
        str: The prefixed work URIs separated by spaces.
    """
    return " ".join(f"r:{work_id}" for work_id in work_ids)


def _chunks(
    items: list[str],
    size: int
) -> Iterator[list[str]]:
    """
    Split a list into consecutive chunks.

    Args:
        items (list[str]): The items to split.
        size (int): The maximum size of a chunk.

    Yields:
        list[str]: The next chunk.
    """
    for start in range(0, len(items), size):
        yield items[start:start + size]
