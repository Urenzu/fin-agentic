"""Detecting what shape of business a filer is, from what it reports.

A financial statement's structure encodes the business model, so a template is
not just a layout -- it binds together statement structure, concept vocabulary,
identity checks, and *which ratios are meaningful*.

That last part is why this module exists. Rendering a bank in a commercial
layout produces a table that looks odd, which is a cosmetic problem. Computing a
bank's current ratio produces a confident number that means nothing, which is a
correctness problem: it is the same harm as a hallucinated figure, reached by a
different route. JPMorgan's assets/equity of 12.5x reads as twice as risky as
Apple's 5.6x, when in fact 12.5x is unremarkable for a bank whose solvency is
governed by Basel capital ratios rather than by leverage.

So shape is detected before anything is rendered, and an unsupported shape is
disclosed rather than approximated.

Detection runs on the raw tag set rather than on an adapted FactSet, because
adaptation drops every tag the commercial map does not know -- which is exactly
the evidence that identifies a non-commercial filer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class EntityShape(StrEnum):
    """The statement structure a filer uses."""

    #: Reg S-X Article 5. Classified balance sheet, gross profit, an operating
    #: cycle. Tech, retail, industrial, healthcare, energy.
    COMMERCIAL = "commercial"
    #: Reg S-X Article 9. Unclassified balance sheet, deposits and loans, net
    #: interest income, provision for credit losses.
    BANK = "bank"
    #: Real estate. GAAP depreciation understates the economics, so FFO rather
    #: than EPS is the headline measure.
    REIT = "reit"
    #: Reg S-X Article 7. Premiums earned, loss reserves, combined ratio.
    INSURER = "insurer"
    #: Nothing matched with enough evidence to commit.
    UNKNOWN = "unknown"


#: Shapes we can currently render and analyse correctly.
SUPPORTED_SHAPES: frozenset[EntityShape] = frozenset({EntityShape.COMMERCIAL})


@dataclass(frozen=True, slots=True)
class ShapeAssessment:
    """What shape a filer is, and how confident we are."""

    shape: EntityShape
    #: Tags that drove the decision, so it can be argued with rather than
    #: taken on faith.
    evidence: tuple[str, ...] = ()
    #: Signals expected for this shape that were absent.
    counter_evidence: tuple[str, ...] = field(default=())

    @property
    def is_supported(self) -> bool:
        return self.shape in SUPPORTED_SHAPES

    @property
    def message(self) -> str:
        if self.shape is EntityShape.COMMERCIAL:
            return "Commercial filer; standard three-statement analysis applies."
        if self.shape is EntityShape.UNKNOWN:
            return (
                "Could not determine this filer's statement structure. Analysis "
                "is limited to figures that validate on their own."
            )
        return (
            f"This is a {self.shape.value} filer. Its statements are structured "
            f"differently from a commercial company -- "
            f"{_WHY_DIFFERENT[self.shape]} Specialised analysis is not yet "
            f"supported, so ratios that would be misleading are withheld rather "
            f"than shown."
        )


_WHY_DIFFERENT: dict[EntityShape, str] = {
    EntityShape.BANK: (
        "it has no operating cycle, so no current/non-current split and no gross "
        "profit, and its deposits are raw material rather than debt."
    ),
    EntityShape.REIT: (
        "GAAP depreciation on real estate systematically understates its "
        "economics, so net income and EPS are poor measures of performance."
    ),
    EntityShape.INSURER: (
        "premiums are collected before claims are paid, so profitability turns on "
        "reserve adequacy rather than on a margin."
    ),
}


#: Tags that only a bank reports. Deposits and net interest income are the
#: defining pair: taking deposits and earning a spread on them *is* the business.
_BANK_MARKERS = (
    "Deposits",
    "InterestIncomeExpenseNet",
    "InterestAndFeeIncomeLoansAndLeases",
    "InterestExpenseDeposits",
    "NoninterestIncome",
    "NoninterestExpense",
    "ProvisionForLoanLeaseAndOtherLosses",
    "ProvisionForLoanAndLeaseLosses",
    "InterestBearingDepositsInBanks",
    "FederalFundsSoldAndSecuritiesPurchasedUnderAgreementsToResell",
    "LoansAndLeasesReceivableNetReportedAmount",
)

_REIT_MARKERS = (
    "RealEstateInvestmentPropertyNet",
    "RealEstateInvestmentPropertyAtCost",
    "RealEstateInvestmentPropertyAccumulatedDepreciation",
    "OperatingLeasesIncomeStatementLeaseRevenue",
    "PaymentsToAcquireRealEstate",
    "TenantReimbursements",
)

_INSURER_MARKERS = (
    "PremiumsEarnedNet",
    "LiabilityForFuturePolicyBenefits",
    "LiabilityForClaimsAndClaimsAdjustmentExpense",
    "PolicyholderBenefitsAndClaimsIncurredNet",
    "DeferredPolicyAcquisitionCosts",
    "IncurredClaimsPropertyCasualtyAndLiability",
)

#: The defining signature of a classified balance sheet. Their absence is the
#: strongest single signal that a filer is not a commercial company.
_CLASSIFIED_MARKERS = ("AssetsCurrent", "LiabilitiesCurrent")

#: How many markers must be present before a specialised shape is asserted. Two
#: guards against a commercial company that happens to report one adjacent tag --
#: a manufacturer with a financing arm reports some interest income without
#: being a bank.
_MIN_MARKERS = 2


def detect_shape(tags: set[str]) -> ShapeAssessment:
    """Infer a filer's statement structure from the tags it reports."""
    scores: list[tuple[EntityShape, tuple[str, ...]]] = []
    for shape, markers in (
        (EntityShape.BANK, _BANK_MARKERS),
        (EntityShape.INSURER, _INSURER_MARKERS),
        (EntityShape.REIT, _REIT_MARKERS),
    ):
        hits = tuple(m for m in markers if m in tags)
        if len(hits) >= _MIN_MARKERS:
            scores.append((shape, hits))

    classified = tuple(m for m in _CLASSIFIED_MARKERS if m in tags)

    if scores:
        # Most evidence wins. A bank holding real estate reports a few REIT-ish
        # tags, but far more banking ones.
        shape, hits = max(scores, key=lambda s: len(s[1]))

        # A classified balance sheet alongside specialised markers usually means
        # a commercial company with a financing or property arm rather than a
        # true specialist. Banks in particular never present one.
        if classified and shape is EntityShape.BANK and len(hits) < 4:
            return ShapeAssessment(
                shape=EntityShape.COMMERCIAL,
                evidence=classified,
                counter_evidence=hits,
            )
        return ShapeAssessment(shape=shape, evidence=hits, counter_evidence=classified)

    if classified:
        return ShapeAssessment(shape=EntityShape.COMMERCIAL, evidence=classified)

    return ShapeAssessment(
        shape=EntityShape.UNKNOWN,
        counter_evidence=tuple(_CLASSIFIED_MARKERS),
    )
