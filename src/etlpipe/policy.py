"""
Policy tables of the transformer: what to keep, drop and how to rename it.

The tables are data files in ``config/`` (hand-maintained CSV plus the generated ``cdm_model.json``), so a decision can be
changed without touching code.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .constants import CDM
from .context import Category

CONFIG_DIR = Path(__file__).resolve().parent / "config"

WEMI_LEVELS = ("work", "expression", "manifestation", "item")


@dataclass(frozen=True)
class PropertyInfo:
    """
    Facts about one CDM property taken from ``cdm_model.json``.

    Attributes:
        kind (str): Property kind: ``o`` = object, ``d`` = datatype, ``a`` = annotation.
        levels (tuple[str, ...]): WEMI levels of the domain.
        chain (tuple[str, ...]): Ancestors, nearest super-property first.
    """
    kind: str  # o = object, d = datatype, a = annotation
    levels: tuple[str, ...]  # WEMI levels of the domain
    chain: tuple[str, ...]  # ancestors, nearest super-property first


@dataclass(frozen=True)
class ClassInfo:
    """
    Facts about one CDM class taken from ``cdm_model.json``.

    Attributes:
        depth (int): Depth of the class in the class hierarchy.
        levels (tuple[str, ...]): WEMI levels the class belongs to.
    """
    depth: int
    levels: tuple[str, ...]


@dataclass(frozen=True)
class RelationRule:
    """
    One row of ``relations.csv``: how a CDM relation maps to a canonical relation.

    Attributes:
        name (str): Local name of the CDM property.
        canonical (str): Canonical relation type; empty if the relation is explicitly excluded.
        invert (bool): Whether the direction is reversed when mapping.
        symmetric (bool): Whether the relation is symmetric.
        category (Category): Category of the relation; the relation is loaded only if its category is enabled in the options.
    """
    name: str
    canonical: str  # "" = explicitly excluded
    invert: bool
    symmetric: bool
    category: Category

    @property
    def excluded(self) -> bool:
        """Whether the relation is explicitly excluded (has no canonical type)."""
        return not self.canonical


@dataclass(frozen=True)
class AttributeRule:
    """
    One row of ``attributes.csv``: how a CDM attribute maps to a ``kms:`` property.

    Attributes:
        name (str): Local name of the CDM property.
        kms (str): Name of the ``kms:`` property; empty if the attribute is dropped.
    """
    name: str
    kms: str  # "" = dropped


@dataclass(frozen=True)
class AnnotationRule:
    """
    One row of ``annotations.csv``: how a relation annotation maps to a ``kms:`` property.

    Attributes:
        name (str): Local name of the CDM annotation property.
        kms (str): Name of the ``kms:`` property; empty if the annotation is dropped.
        identity (bool): Whether the annotation is part of the edge identity (locator).
    """
    name: str
    kms: str  # "" = dropped
    identity: bool  # part of the edge identity (locator)


class Policy:
    """
    The policy tables loaded from the config directory.

    Args:
        config_dir (Path): Directory with ``cdm_model.json`` and the CSV tables. Default ``CONFIG_DIR``.
    """

    def __init__(
        self,
        config_dir: Path = CONFIG_DIR
    ) -> None:
        model = json.loads((config_dir / "cdm_model.json").read_text(encoding="utf-8"))
        self.properties: dict[str, PropertyInfo] = {
            n: PropertyInfo(v[0], tuple(v[1]), tuple(v[2])) for n, v in model["properties"].items()
        }
        self.classes: dict[str, ClassInfo] = {n: ClassInfo(v[0], tuple(v[1])) for n, v in model["classes"].items()}
        self.relations = {
            r["name"]: RelationRule(r["name"], r["canonical"], r["invert"] == "1", r["symmetric"] == "1", Category(r["category"]))
            for r in _rows(config_dir / "relations.csv")
        }
        self.attributes = {r["name"]: AttributeRule(r["name"], r["kms"]) for r in _rows(config_dir / "attributes.csv")}
        self.annotations = {r["name"]: AnnotationRule(r["name"], r["kms"], r["identity"] == "1")
                            for r in _rows(config_dir / "annotations.csv")}
        self.technical_types = {r["name"] for r in _rows(config_dir / "doc_types.csv") if r["role"] == "technical"}

    @staticmethod
    def cdm_local(
        uri: str
    ) -> Optional[str]:
        """
        Get the local name of a CDM URI.

        Args:
            uri (str): The URI to shorten.

        Returns:
            Optional[str]: The part after the CDM namespace, or None if the URI is not in the CDM namespace.
        """
        s = str(uri)
        return s[len(CDM):] if s.startswith(str(CDM)) else None

    def chain(
        self,
        local: str
    ) -> tuple[str, ...]:
        """
        Get the property followed by its super-properties, nearest first.

        Args:
            local (str): Local name of the property.

        Returns:
            tuple[str, ...]: The property and its ancestors.
        """
        info = self.properties.get(local)
        return (local,) + (info.chain if info else ())

    def relation_rule(
        self,
        local: str
    ) -> Optional[RelationRule]:
        """
        Get the rule of a relation.

        Among the entries of relations.csv on the property's super-property chain the most specific one wins
        (the one with the longest chain of its own), so ``event_contains_work`` overrides ``contains``.

        Args:
            local (str): Local name of the property.

        Returns:
            Optional[RelationRule]: The matching rule, or None if no entry applies.
        """
        matches = [n for n in self.chain(local) if n in self.relations]
        if not matches:
            return None
        return self.relations[max(matches, key=lambda n: len(self.chain(n)))]

    def attribute_rule(
        self,
        local: str
    ) -> Optional[AttributeRule]:
        """
        Get the rule of an attribute, taken from the nearest entry on the property's super-property chain.

        Args:
            local (str): Local name of the property.

        Returns:
            Optional[AttributeRule]: The matching rule, or None if no entry applies.
        """
        return next((self.attributes[n] for n in self.chain(local) if n in self.attributes), None)

    def property_levels(
        self,
        local: str
    ) -> tuple[str, ...]:
        """
        Get the WEMI levels of a property's domain.

        Args:
            local (str): Local name of the property.

        Returns:
            tuple[str, ...]: The levels, empty if the property is unknown.
        """
        info = self.properties.get(local)
        return info.levels if info else ()

    def class_levels(
        self,
        local: str
    ) -> tuple[str, ...]:
        """
        Get the WEMI levels of a class.

        Args:
            local (str): Local name of the class.

        Returns:
            tuple[str, ...]: The levels, empty if the class is unknown.
        """
        info = self.classes.get(local)
        return info.levels if info else ()


def _rows(
    path: Path
) -> list[dict[str, str]]:
    """
    Read a CSV file into a list of rows.

    Args:
        path (Path): The CSV file to read.

    Returns:
        list[dict[str, str]]: One dictionary per row, keyed by the header.
    """
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@lru_cache(maxsize=1)
def load_policy() -> Policy:
    """
    Get the shared :class:`Policy` instance, loaded once from the default config directory.

    Returns:
        Policy: The cached policy.
    """
    return Policy()