"""How much of a company's history EDGAR actually holds.

This is all the entity card needs, and all that survived the canonical ledger.
The ledger computed the same summary as a by-product of mapping every
observation onto a concept vocabulary, adapting periods and reconciling
restatements -- thousands of lines of machinery to answer four questions that
the raw observations answer directly.

Nothing here maps anything. An observation carries a date and the accession it
came from, which is enough to say how far back the filings go and how many
annual reports there are, and neither answer improves for having been through a
vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from finagentic.ingest.edgar import XbrlObservation

#: Forms that constitute an annual report. A filer's history is measured in
#: these: a company with twenty years of 10-Qs and no 10-K has not been
#: reporting annually, whatever its date range suggests.
ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "20-F/A", "40-F"})

#: A registrant filing less than this much history is almost certainly not the
#: entity the user meant. Set just above two years so a genuine recent IPO is
#: flagged too -- in that case the flag is still correct, since there really is
#: no long history to analyse.
MIN_EXPECTED_HISTORY_YEARS = 2.5


@dataclass(frozen=True, slots=True)
class Coverage:
    """What the filings span, so a thin history is visible rather than implied."""

    earliest: date | None = None
    latest: date | None = None
    annual_reports: int = 0
    #: Observations EDGAR published for this filer, as a sense of ledger size.
    observations: int = 0

    @property
    def history_years(self) -> float:
        if self.earliest is None or self.latest is None:
            return 0.0
        return (self.latest - self.earliest).days / 365.25

    @property
    def looks_truncated(self) -> bool:
        """Whether this history is too thin to be the company the user meant.

        A ticker resolves to whichever CIK currently holds it. After a corporate
        reorganisation that is the new holding company, whose history begins at
        the reorganisation -- so `XOM` returns a few months of data while the
        decades of Exxon Mobil filings sit under the predecessor CIK.

        Returning that quietly would be the exact failure this system exists to
        prevent: not a wrong number, but a confident-looking answer built on
        almost no data. Callers must surface this rather than render a chart.
        """
        return self.history_years < MIN_EXPECTED_HISTORY_YEARS or self.annual_reports == 0


def summarise(observations: list[XbrlObservation]) -> Coverage:
    """Summarise a filer's published history.

    Annual reports are counted by distinct accession rather than by counting
    annual revenue figures, which is what the ledger did. An accession is one
    submission, so counting them cannot be thrown off by a filer who tags
    revenue under an element the vocabulary happened not to carry.
    """
    if not observations:
        return Coverage()

    annual = {o.accession for o in observations if o.form in ANNUAL_FORMS}
    ends = [o.end for o in observations]

    return Coverage(
        earliest=min(ends),
        latest=max(ends),
        annual_reports=len(annual),
        observations=len(observations),
    )


__all__ = ["ANNUAL_FORMS", "MIN_EXPECTED_HISTORY_YEARS", "Coverage", "summarise"]
