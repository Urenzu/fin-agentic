"""Entity shape detection.

The stakes here are higher than layout. Rendering a bank in a commercial table
looks odd, which is cosmetic. Computing a bank's current ratio produces a
confident number that means nothing, which is the same harm as a hallucinated
figure by a different route -- so an unsupported shape must be detected and
disclosed, never approximated.

Tag sets below are trimmed from real filings.
"""

from __future__ import annotations

from finagentic.ingest.shapes import EntityShape, detect_shape

COMMERCIAL_TAGS = {
    "Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent",
    "StockholdersEquity", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "CostOfGoodsAndServicesSold", "GrossProfit", "InventoryNet",
}

BANK_TAGS = {
    "Assets", "Liabilities", "StockholdersEquity", "Deposits",
    "InterestIncomeExpenseNet", "InterestAndFeeIncomeLoansAndLeases",
    "InterestExpenseDeposits", "NoninterestIncome", "NoninterestExpense",
    "ProvisionForLoanLeaseAndOtherLosses",
}

REIT_TAGS = {
    "Assets", "Liabilities", "StockholdersEquity",
    "RealEstateInvestmentPropertyNet", "RealEstateInvestmentPropertyAtCost",
    "RealEstateInvestmentPropertyAccumulatedDepreciation",
    "PaymentsToAcquireRealEstate",
}

INSURER_TAGS = {
    "Assets", "Liabilities", "StockholdersEquity", "PremiumsEarnedNet",
    "LiabilityForFuturePolicyBenefits", "DeferredPolicyAcquisitionCosts",
    "IncurredClaimsPropertyCasualtyAndLiability",
}


def test_a_classified_balance_sheet_means_commercial():
    assert detect_shape(COMMERCIAL_TAGS).shape is EntityShape.COMMERCIAL


def test_deposits_and_net_interest_income_mean_bank():
    assessment = detect_shape(BANK_TAGS)
    assert assessment.shape is EntityShape.BANK
    assert "Deposits" in assessment.evidence


def test_a_bank_is_not_currently_supported():
    """Until a bank template exists, analysis must be withheld, not approximated."""
    assessment = detect_shape(BANK_TAGS)
    assert not assessment.is_supported
    assert "not yet supported" in assessment.message


def test_the_bank_message_explains_why_it_differs():
    """A user told "unsupported" with no reason will assume the tool is broken."""
    message = detect_shape(BANK_TAGS).message
    assert "operating cycle" in message
    assert "deposits" in message.lower()


def test_real_estate_holdings_mean_reit():
    assert detect_shape(REIT_TAGS).shape is EntityShape.REIT


def test_policy_reserves_mean_insurer():
    assert detect_shape(INSURER_TAGS).shape is EntityShape.INSURER


def test_a_commercial_filer_is_supported():
    assessment = detect_shape(COMMERCIAL_TAGS)
    assert assessment.is_supported
    assert "standard three-statement" in assessment.message


def test_one_stray_marker_does_not_reclassify_a_commercial_filer():
    """A manufacturer with a financing arm reports some interest income without
    being a bank. A single marker must not outweigh a classified balance sheet."""
    tags = COMMERCIAL_TAGS | {"NoninterestIncome"}
    assert detect_shape(tags).shape is EntityShape.COMMERCIAL


def test_a_classified_balance_sheet_outweighs_weak_bank_evidence():
    """Banks never present a classified balance sheet, so its presence alongside
    only a couple of banking tags means a commercial filer with a lending arm."""
    tags = COMMERCIAL_TAGS | {"NoninterestIncome", "InterestExpenseDeposits"}
    assessment = detect_shape(tags)
    assert assessment.shape is EntityShape.COMMERCIAL
    assert assessment.counter_evidence  # the banking tags are still recorded


def test_strong_bank_evidence_wins_even_with_a_current_split():
    tags = BANK_TAGS | {"AssetsCurrent", "LiabilitiesCurrent"}
    assert detect_shape(tags).shape is EntityShape.BANK


def test_nothing_recognisable_is_unknown_not_commercial():
    """Defaulting an unrecognised filer to commercial would apply the wrong
    ratios silently, which is exactly what this module exists to prevent."""
    assessment = detect_shape({"Assets", "Liabilities", "SomeExoticTag"})
    assert assessment.shape is EntityShape.UNKNOWN
    assert not assessment.is_supported


def test_an_empty_tag_set_is_unknown():
    assert detect_shape(set()).shape is EntityShape.UNKNOWN


def test_the_shape_with_the_most_evidence_wins():
    """A bank holding property reports a few real-estate tags and many banking
    ones; weight of evidence should settle it."""
    tags = BANK_TAGS | {"RealEstateInvestmentPropertyNet", "PaymentsToAcquireRealEstate"}
    assert detect_shape(tags).shape is EntityShape.BANK
