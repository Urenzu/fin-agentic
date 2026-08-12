"""Mapping us-gaap tags onto canonical concepts.

Why this is needed
------------------
Filers do not use one tag per idea. Apple's top line alone moved across three
tags in fifteen years:

    SalesRevenueNet                                      FY2009-2018
    Revenues                                             FY2018
    RevenueFromContractWithCustomerExcludingAssessedTax  FY2019-2026

Charting a single tag therefore produces a revenue history that collapses to
zero in 2019 -- not because anything happened to Apple, but because ASC 606
changed the tag. Every filer has some version of this problem, and it is the
single largest source of wrong-looking time series in naive XBRL tooling.

So tags are aliased onto the canonical `Concept` vocabulary. The mapping is a
plain dictionary rather than anything learned or inferred: it is auditable, it
is testable, and a wrong entry is a one-line fix. Where several tags map to one
concept, `TAG_PRECEDENCE` decides which to believe when a filing reports more
than one for the same period.

Unmapped tags are not an error. A filer's 500 tags include segment detail,
footnote disclosures and dimensional breakouts that have no place in a
three-statement view. They are simply not ingested, and `unmapped_tags()`
reports them so the map can be extended deliberately.
"""

from __future__ import annotations

from collections import defaultdict

from finagentic.domain.concepts import Concept

#: us-gaap tag -> canonical concept.
TAG_TO_CONCEPT: dict[str, Concept] = {
    # ---- revenue ----------------------------------------------------------
    "RevenueFromContractWithCustomerExcludingAssessedTax": Concept.REVENUE,
    "RevenueFromContractWithCustomerIncludingAssessedTax": Concept.REVENUE,
    "Revenues": Concept.REVENUE,
    "SalesRevenueNet": Concept.REVENUE,
    "SalesRevenueGoodsNet": Concept.REVENUE,
    "SalesRevenueServicesNet": Concept.REVENUE,
    # ---- cost of revenue --------------------------------------------------
    "CostOfRevenue": Concept.COST_OF_REVENUE,
    "CostOfGoodsAndServicesSold": Concept.COST_OF_REVENUE,
    "CostOfGoodsSold": Concept.COST_OF_REVENUE,
    "CostOfServices": Concept.COST_OF_REVENUE,
    "GrossProfit": Concept.GROSS_PROFIT,
    # ---- operating expenses ----------------------------------------------
    "ResearchAndDevelopmentExpense": Concept.RESEARCH_AND_DEVELOPMENT,
    "SellingGeneralAndAdministrativeExpense": Concept.SELLING_GENERAL_ADMIN,
    "GeneralAndAdministrativeExpense": Concept.GENERAL_AND_ADMIN,
    "SellingAndMarketingExpense": Concept.SALES_AND_MARKETING,
    "MarketingAndAdvertisingExpense": Concept.SALES_AND_MARKETING,
    "OtherCostAndExpenseOperating": Concept.OTHER_OPERATING_EXPENSE,
    "OperatingExpenses": Concept.TOTAL_OPERATING_EXPENSES,
    # ---- income ----------------------------------------------------------
    "OperatingIncomeLoss": Concept.OPERATING_INCOME,
    "InterestExpense": Concept.INTEREST_EXPENSE,
    "InterestExpenseNonoperating": Concept.INTEREST_EXPENSE,
    "InvestmentIncomeInterest": Concept.INTEREST_INCOME,
    "NonoperatingIncomeExpense": Concept.OTHER_NONOPERATING_INCOME,
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": Concept.PRETAX_INCOME,
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments": Concept.PRETAX_INCOME,
    "IncomeTaxExpenseBenefit": Concept.INCOME_TAX_EXPENSE,
    "NetIncomeLoss": Concept.NET_INCOME,
    "ProfitLoss": Concept.NET_INCOME_INCLUDING_NCI,
    "NetIncomeLossAttributableToNoncontrollingInterest": Concept.NET_INCOME_TO_NCI,
    "NetIncomeLossAvailableToCommonStockholdersBasic": Concept.NET_INCOME_TO_COMMON,
    "EarningsPerShareBasic": Concept.EPS_BASIC,
    "EarningsPerShareDiluted": Concept.EPS_DILUTED,
    "WeightedAverageNumberOfSharesOutstandingBasic": Concept.SHARES_BASIC,
    "WeightedAverageNumberOfDilutedSharesOutstanding": Concept.SHARES_DILUTED,
    # ---- current assets ---------------------------------------------------
    "CashAndCashEquivalentsAtCarryingValue": Concept.CASH_AND_EQUIVALENTS,
    "ShortTermInvestments": Concept.SHORT_TERM_INVESTMENTS,
    "MarketableSecuritiesCurrent": Concept.SHORT_TERM_INVESTMENTS,
    "AvailableForSaleSecuritiesCurrent": Concept.SHORT_TERM_INVESTMENTS,
    "AccountsReceivableNetCurrent": Concept.ACCOUNTS_RECEIVABLE,
    "ReceivablesNetCurrent": Concept.ACCOUNTS_RECEIVABLE,
    "InventoryNet": Concept.INVENTORY,
    "PrepaidExpenseAndOtherAssetsCurrent": Concept.PREPAID_EXPENSES,
    "PrepaidExpenseCurrent": Concept.PREPAID_EXPENSES,
    "OtherAssetsCurrent": Concept.OTHER_CURRENT_ASSETS,
    "AssetsCurrent": Concept.TOTAL_CURRENT_ASSETS,
    # ---- non-current assets ----------------------------------------------
    "PropertyPlantAndEquipmentNet": Concept.PROPERTY_PLANT_EQUIPMENT_NET,
    "LongTermInvestments": Concept.LONG_TERM_INVESTMENTS,
    "MarketableSecuritiesNoncurrent": Concept.LONG_TERM_INVESTMENTS,
    "Goodwill": Concept.GOODWILL,
    "IntangibleAssetsNetExcludingGoodwill": Concept.INTANGIBLE_ASSETS,
    "FiniteLivedIntangibleAssetsNet": Concept.INTANGIBLE_ASSETS,
    "OperatingLeaseRightOfUseAsset": Concept.OPERATING_LEASE_ROU_ASSET,
    "OtherAssetsNoncurrent": Concept.OTHER_NONCURRENT_ASSETS,
    "AssetsNoncurrent": Concept.TOTAL_NONCURRENT_ASSETS,
    "Assets": Concept.TOTAL_ASSETS,
    # ---- current liabilities ---------------------------------------------
    "AccountsPayableCurrent": Concept.ACCOUNTS_PAYABLE,
    "AccountsPayableAndAccruedLiabilitiesCurrent": Concept.ACCOUNTS_PAYABLE,
    "AccruedLiabilitiesCurrent": Concept.ACCRUED_LIABILITIES,
    "EmployeeRelatedLiabilitiesCurrent": Concept.ACCRUED_LIABILITIES,
    "ContractWithCustomerLiabilityCurrent": Concept.DEFERRED_REVENUE_CURRENT,
    "DeferredRevenueCurrent": Concept.DEFERRED_REVENUE_CURRENT,
    "ShortTermBorrowings": Concept.SHORT_TERM_DEBT,
    "CommercialPaper": Concept.SHORT_TERM_DEBT,
    "LongTermDebtCurrent": Concept.CURRENT_PORTION_LONG_TERM_DEBT,
    "OtherLiabilitiesCurrent": Concept.OTHER_CURRENT_LIABILITIES,
    "LiabilitiesCurrent": Concept.TOTAL_CURRENT_LIABILITIES,
    # ---- non-current liabilities -----------------------------------------
    "LongTermDebtNoncurrent": Concept.LONG_TERM_DEBT,
    "LongTermDebt": Concept.LONG_TERM_DEBT,
    "OperatingLeaseLiabilityNoncurrent": Concept.OPERATING_LEASE_LIABILITY_NONCURRENT,
    "DeferredIncomeTaxLiabilitiesNet": Concept.DEFERRED_TAX_LIABILITIES,
    "DeferredTaxLiabilitiesNoncurrent": Concept.DEFERRED_TAX_LIABILITIES,
    "OtherLiabilitiesNoncurrent": Concept.OTHER_NONCURRENT_LIABILITIES,
    "LiabilitiesNoncurrent": Concept.TOTAL_NONCURRENT_LIABILITIES,
    "Liabilities": Concept.TOTAL_LIABILITIES,
    # ---- equity -----------------------------------------------------------
    "CommonStocksIncludingAdditionalPaidInCapital": Concept.COMMON_STOCK_AND_APIC,
    "AdditionalPaidInCapital": Concept.COMMON_STOCK_AND_APIC,
    "CommonStockValue": Concept.COMMON_STOCK_AND_APIC,
    "RetainedEarningsAccumulatedDeficit": Concept.RETAINED_EARNINGS,
    "TreasuryStockValue": Concept.TREASURY_STOCK,
    "TreasuryStockCommonValue": Concept.TREASURY_STOCK,
    "AccumulatedOtherComprehensiveIncomeLossNetOfTax": Concept.ACCUMULATED_OCI,
    "StockholdersEquity": Concept.TOTAL_STOCKHOLDERS_EQUITY,
    "MinorityInterest": Concept.MINORITY_INTEREST,
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": Concept.TOTAL_EQUITY_INCL_MINORITY,
    "LiabilitiesAndStockholdersEquity": Concept.TOTAL_LIABILITIES_AND_EQUITY,
    # ---- operating cash flow ---------------------------------------------
    "DepreciationDepletionAndAmortization": Concept.DEPRECIATION_AND_AMORTIZATION,
    "DepreciationAmortizationAndAccretionNet": Concept.DEPRECIATION_AND_AMORTIZATION,
    "DepreciationAndAmortization": Concept.DEPRECIATION_AND_AMORTIZATION,
    "ShareBasedCompensation": Concept.STOCK_BASED_COMPENSATION,
    "DeferredIncomeTaxExpenseBenefit": Concept.DEFERRED_INCOME_TAXES,
    "IncreaseDecreaseInAccountsReceivable": Concept.CHANGE_IN_RECEIVABLES,
    "IncreaseDecreaseInInventories": Concept.CHANGE_IN_INVENTORY,
    "IncreaseDecreaseInAccountsPayable": Concept.CHANGE_IN_PAYABLES,
    "IncreaseDecreaseInContractWithCustomerLiability": Concept.CHANGE_IN_DEFERRED_REVENUE,
    "IncreaseDecreaseInDeferredRevenue": Concept.CHANGE_IN_DEFERRED_REVENUE,
    "OtherOperatingActivitiesCashFlowStatement": Concept.OTHER_OPERATING_ACTIVITIES,
    "NetCashProvidedByUsedInOperatingActivities": Concept.NET_CASH_OPERATING,
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": Concept.NET_CASH_OPERATING,
    # ---- investing cash flow ---------------------------------------------
    "PaymentsToAcquirePropertyPlantAndEquipment": Concept.CAPITAL_EXPENDITURES,
    "PaymentsToAcquireProductiveAssets": Concept.CAPITAL_EXPENDITURES,
    "PaymentsToAcquireBusinessesNetOfCashAcquired": Concept.ACQUISITIONS_NET_OF_CASH,
    "PaymentsToAcquireInvestments": Concept.PURCHASES_OF_INVESTMENTS,
    "PaymentsToAcquireAvailableForSaleSecuritiesDebt": Concept.PURCHASES_OF_INVESTMENTS,
    "ProceedsFromSaleMaturityAndCollectionsOfInvestments": Concept.SALES_MATURITIES_OF_INVESTMENTS,
    "PaymentsForProceedsFromOtherInvestingActivities": Concept.OTHER_INVESTING_ACTIVITIES,
    "NetCashProvidedByUsedInInvestingActivities": Concept.NET_CASH_INVESTING,
    "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations": Concept.NET_CASH_INVESTING,
    # ---- financing cash flow ---------------------------------------------
    "ProceedsFromIssuanceOfDebt": Concept.DEBT_ISSUED,
    "ProceedsFromIssuanceOfLongTermDebt": Concept.DEBT_ISSUED,
    "RepaymentsOfDebt": Concept.DEBT_REPAID,
    "RepaymentsOfLongTermDebt": Concept.DEBT_REPAID,
    "PaymentsForRepurchaseOfCommonStock": Concept.SHARE_REPURCHASES,
    "PaymentsOfDividends": Concept.DIVIDENDS_PAID,
    "PaymentsOfDividendsCommonStock": Concept.DIVIDENDS_PAID,
    "ProceedsFromPaymentsForOtherFinancingActivities": Concept.OTHER_FINANCING_ACTIVITIES,
    "NetCashProvidedByUsedInFinancingActivities": Concept.NET_CASH_FINANCING,
    "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations": Concept.NET_CASH_FINANCING,
    # ---- cash reconciliation ---------------------------------------------
    "EffectOfExchangeRateOnCashAndCashEquivalents": Concept.FX_EFFECT_ON_CASH,
    "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": Concept.FX_EFFECT_ON_CASH,
    "CashAndCashEquivalentsPeriodIncreaseDecrease": Concept.NET_CHANGE_IN_CASH,
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": Concept.NET_CHANGE_IN_CASH,
}


#: When one filing reports several aliases of the same concept for the same
#: period, prefer the tag appearing earliest in this list. Ordering rationale:
#: the most specific, most current tag wins, since a filer emitting both
#: `RevenueFromContractWithCustomerExcludingAssessedTax` and the legacy
#: `Revenues` is using the former as the real line and the latter as a rollup.
TAG_PRECEDENCE: dict[Concept, tuple[str, ...]] = {
    Concept.REVENUE: (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
    ),
    Concept.COST_OF_REVENUE: (
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
        "CostOfServices",
    ),
    Concept.LONG_TERM_DEBT: ("LongTermDebtNoncurrent", "LongTermDebt"),
    Concept.COMMON_STOCK_AND_APIC: (
        "CommonStocksIncludingAdditionalPaidInCapital",
        "AdditionalPaidInCapital",
        "CommonStockValue",
    ),
    Concept.DEPRECIATION_AND_AMORTIZATION: (
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
    ),
    Concept.NET_CASH_OPERATING: (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    Concept.NET_CASH_INVESTING: (
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
    ),
    Concept.NET_CASH_FINANCING: (
        "NetCashProvidedByUsedInFinancingActivities",
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
    ),
    Concept.SHORT_TERM_INVESTMENTS: (
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesCurrent",
    ),
    Concept.DEFERRED_REVENUE_CURRENT: (
        "ContractWithCustomerLiabilityCurrent",
        "DeferredRevenueCurrent",
    ),
    Concept.CHANGE_IN_DEFERRED_REVENUE: (
        "IncreaseDecreaseInContractWithCustomerLiability",
        "IncreaseDecreaseInDeferredRevenue",
    ),
    Concept.CAPITAL_EXPENDITURES: (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    Concept.ACCOUNTS_PAYABLE: (
        "AccountsPayableCurrent",
        "AccountsPayableAndAccruedLiabilitiesCurrent",
    ),
}


def concept_for(tag: str) -> Concept | None:
    """Return the canonical concept for `tag`, or None if it is not mapped."""
    return TAG_TO_CONCEPT.get(tag)


def tags_for(concept: Concept) -> list[str]:
    """Every tag that maps onto `concept`, in precedence order."""
    ranked = TAG_PRECEDENCE.get(concept)
    if ranked is not None:
        return list(ranked)
    return sorted(t for t, c in TAG_TO_CONCEPT.items() if c is concept)


def tag_rank(concept: Concept, tag: str) -> int:
    """Precedence of `tag` for `concept`; lower wins.

    Tags with no explicit ordering sort after those that have one, so an
    unranked alias never displaces a deliberately preferred tag.
    """
    ranked = TAG_PRECEDENCE.get(concept, ())
    return ranked.index(tag) if tag in ranked else len(ranked)


def unmapped_tags(tags: set[str]) -> list[str]:
    """Tags present in the data that this map does not cover.

    Used to grow the map deliberately: run it over a corpus and look at what
    turns up frequently, rather than guessing at what filers use.
    """
    return sorted(t for t in tags if t not in TAG_TO_CONCEPT)


def aliases_by_concept() -> dict[Concept, list[str]]:
    """Inverse of the map, for inspection and tests."""
    out: dict[Concept, list[str]] = defaultdict(list)
    for tag, concept in TAG_TO_CONCEPT.items():
        out[concept].append(tag)
    return dict(out)


# Every tag listed in TAG_PRECEDENCE must also appear in TAG_TO_CONCEPT, and must
# map to the concept it claims to rank for. A typo here would silently disable
# precedence for that concept, so it is caught at import time.
for _concept, _ranked in TAG_PRECEDENCE.items():
    for _tag in _ranked:
        if TAG_TO_CONCEPT.get(_tag) is not _concept:  # pragma: no cover
            raise RuntimeError(
                f"TAG_PRECEDENCE lists {_tag!r} under {_concept}, but TAG_TO_CONCEPT "
                f"maps it to {TAG_TO_CONCEPT.get(_tag)}"
            )
