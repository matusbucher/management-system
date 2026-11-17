from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .constants import DEFAULT_WEMI_LEVELS, WEMILevel
from .report import StepReport, TransformReport


class Category(Enum):
    """
    Categories of relations (config/relations.csv).
    """
    LEGAL = "legal"
    CLASSIFICATION = "classification"
    AGENT = "agent"
    CONTEXT = "context"
    ACTOR = "actor"
    LANGUAGE = "language"
    LIFECYCLE = "lifecycle"
    STRUCTURAL = "structural"  # WEMI plumbing; only used by excluded relations, so never part of the include sets below
class CanonicalScheme(Enum):
    """
    Identifier schemes usable for the canonical URI of a work.
    """
    CELEX = "celex"
    CELLAR = "cellar"

ALL_CATEGORIES = frozenset({
    Category.LEGAL,
    Category.CLASSIFICATION,
    Category.AGENT,
    Category.CONTEXT,
    Category.ACTOR,
    Category.LANGUAGE,
    Category.LIFECYCLE
})

DEFAULT_CATEGORIES = frozenset({
    Category.LEGAL,
    Category.CLASSIFICATION,
    Category.AGENT
})


@dataclass(frozen=True)
class TransformOptions:
    """
    Options of the transformer chain.

    Attributes:
        wemi_levels (frozenset[WEMILevel]): WEMI levels to keep. Nodes of other levels (expressions, manifestations,
            items) are removed.
        include_categories (frozenset[Category]): relation categories (config/relations.csv) to keep.
        canonical_scheme (CanonicalScheme): preferred identifier for the canonical URI of a work: "celex" or "cellar".
        citation_source_kinds (Optional[frozenset[str]]): if set, only works of these kinds (see
            ``uris.celex_source_kind``, e.g. ``{"legislation", "consolidated"}``) may be the source of a CITES edge;
            ``None`` keeps all citations.
        keep_system_metadata (bool): keep Cellar creation/modification timestamps (cmr:*). By default, they are not
            kept.
    """
    wemi_levels: frozenset[WEMILevel] = DEFAULT_WEMI_LEVELS
    include_categories: frozenset[Category] = DEFAULT_CATEGORIES
    canonical_scheme: CanonicalScheme = CanonicalScheme.CELEX
    citation_source_kinds: Optional[frozenset[str]] = None
    keep_system_metadata: bool = False


@dataclass
class TransformContext:
    """
    Passed to every transformer step: options, the statistics sink and the identity of the document being processed.

    Attributes:
        options (TransformOptions): options of the transformer chain.
        source (str): identity of the document being processed.
        report (TransformReport): statistics sink for the current transformation.
        _current (Optional[StepReport]): statistics sink of the currently running step (not part of the public API).
    """
    options: TransformOptions = field(default_factory=TransformOptions)
    source: str = ""
    report: TransformReport = field(default_factory=TransformReport)

    # Currently running step's statistics sink (not part of the public API).
    _current: Optional[StepReport] = field(default=None, repr=False)

    @property
    def stats(self) -> StepReport:
        """
        Statistics sink of the step that is currently running (an ad-hoc one when a step is used on its own).

        Returns:
            StepReport: statistics sink of the currently running step.
        """
        if self._current is None:
            self._current = self.report.begin("adhoc", 0)
        return self._current

    def begin_step(
        self,
        name: str,
        triples_in: int
    ) -> StepReport:
        """
        Begin a new transformation step.

        Args:
            name (str): name of the step.
            triples_in (int): number of input triples for the step.

        Returns:
            StepReport: statistics sink for the new step.
        """
        self._current = self.report.begin(name, triples_in)
        return self._current


@dataclass
class LoadContext:
    """
    Context for the loading phase of the ETL pipeline.

    Attributes:
        source (str): identity of the document being loaded.
        dry_run (bool): if True, the loading will be simulated without making any changes.
    """
    source: str = ""
    dry_run: bool = False