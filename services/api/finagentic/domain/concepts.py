"""Canonical financial concept taxonomy.

Every extracted number is mapped onto exactly one `Concept` from this registry.
The registry is deliberately a *curated subset* of US-GAAP rather than the full
taxonomy: the validators and analytics engine need to reason about relationships
between concepts mechanically, which is only tractable over a closed vocabulary.

Two properties carry most of the weight:

`sign`
    How the value is stored, independent of how the source document printed it.

    MAGNITUDE   -> stored as a non-negative magnitude. Costs, expenses, capital
                   expenditures, dividends paid and buybacks are all stored
                   positive even when the filing prints "(45,678)". This means a
                   formula can always be written the natural way,
                   e.g. GrossProfit = Revenue - CostOfRevenue.
    AS_REPORTED -> the printed sign is preserved because the sign is genuine
                   information. Net income can be a loss; operating cash flow can
                   be negative; retained earnings can be a deficit.

    Extraction records `sign_flipped` whenever it normalises a printed negative
    into a MAGNITUDE concept, so the transformation is always auditable.

`period_kind`
    INSTANT concepts are measured at a point in time (balance sheet).
    DURATION concepts are measured over a span (income statement, cash flow).
    A fact whose period kind disagrees with its concept is rejected at
    construction time -- this catches a whole class of extraction error where a
    balance sheet column header is misread as a fiscal period.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace as _replace
from enum import StrEnum


class Statement(StrEnum):
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    EQUITY = "equity"
    SUPPLEMENTAL = "supplemental"


class SignConvention(StrEnum):
    MAGNITUDE = "magnitude"
    AS_REPORTED = "as_reported"


class PeriodKind(StrEnum):
    INSTANT = "instant"
    DURATION = "duration"


class Unit(StrEnum):
    USD = "USD"
    SHARES = "shares"
    USD_PER_SHARE = "USD/share"
    RATIO = "ratio"


class Concept(StrEnum):
    # ---- Income statement -------------------------------------------------
    REVENUE = "Revenue"
    COST_OF_REVENUE = "CostOfRevenue"
    GROSS_PROFIT = "GrossProfit"
    RESEARCH_AND_DEVELOPMENT = "ResearchAndDevelopmentExpense"
    SELLING_GENERAL_ADMIN = "SellingGeneralAndAdministrativeExpense"
    SALES_AND_MARKETING = "SellingAndMarketingExpense"
    GENERAL_AND_ADMIN = "GeneralAndAdministrativeExpense"
    OTHER_OPERATING_EXPENSE = "OtherOperatingExpense"
    TOTAL_OPERATING_EXPENSES = "OperatingExpenses"
    OPERATING_INCOME = "OperatingIncomeLoss"
    INTEREST_EXPENSE = "InterestExpense"
    INTEREST_INCOME = "InvestmentIncomeInterest"
    OTHER_NONOPERATING_INCOME = "OtherNonoperatingIncomeExpense"
    PRETAX_INCOME = "IncomeLossBeforeIncomeTaxes"
    INCOME_TAX_EXPENSE = "IncomeTaxExpenseBenefit"
    #: Net income attributable to the parent. This is the "net income" a reader
    #: means, and the numerator of EPS.
    NET_INCOME = "NetIncomeLoss"
    #: Consolidated net income including the share owned by non-controlling
    #: interests. Distinct from NET_INCOME, and the two differ materially for any
    #: company with consolidated subsidiaries it does not wholly own. This is the
    #: figure that equals pre-tax income less tax.
    NET_INCOME_INCLUDING_NCI = "ProfitLoss"
    #: The portion of consolidated net income belonging to non-controlling
    #: interests: NET_INCOME_INCLUDING_NCI - NET_INCOME.
    NET_INCOME_TO_NCI = "NetIncomeLossAttributableToNoncontrollingInterest"
    NET_INCOME_TO_COMMON = "NetIncomeLossAvailableToCommonStockholdersBasic"
    EPS_BASIC = "EarningsPerShareBasic"
    EPS_DILUTED = "EarningsPerShareDiluted"
    SHARES_BASIC = "WeightedAverageNumberOfSharesOutstandingBasic"
    SHARES_DILUTED = "WeightedAverageNumberOfDilutedSharesOutstanding"

    # ---- Balance sheet: assets -------------------------------------------
    CASH_AND_EQUIVALENTS = "CashAndCashEquivalentsAtCarryingValue"
    SHORT_TERM_INVESTMENTS = "ShortTermInvestments"
    ACCOUNTS_RECEIVABLE = "AccountsReceivableNetCurrent"
    INVENTORY = "InventoryNet"
    PREPAID_EXPENSES = "PrepaidExpenseAndOtherAssetsCurrent"
    OTHER_CURRENT_ASSETS = "OtherAssetsCurrent"
    TOTAL_CURRENT_ASSETS = "AssetsCurrent"
    PROPERTY_PLANT_EQUIPMENT_NET = "PropertyPlantAndEquipmentNet"
    LONG_TERM_INVESTMENTS = "LongTermInvestments"
    GOODWILL = "Goodwill"
    INTANGIBLE_ASSETS = "IntangibleAssetsNetExcludingGoodwill"
    OPERATING_LEASE_ROU_ASSET = "OperatingLeaseRightOfUseAsset"
    OTHER_NONCURRENT_ASSETS = "OtherAssetsNoncurrent"
    TOTAL_NONCURRENT_ASSETS = "AssetsNoncurrent"
    TOTAL_ASSETS = "Assets"

    # ---- Balance sheet: liabilities & equity ------------------------------
    ACCOUNTS_PAYABLE = "AccountsPayableCurrent"
    ACCRUED_LIABILITIES = "AccruedLiabilitiesCurrent"
    DEFERRED_REVENUE_CURRENT = "ContractWithCustomerLiabilityCurrent"
    SHORT_TERM_DEBT = "ShortTermBorrowings"
    CURRENT_PORTION_LONG_TERM_DEBT = "LongTermDebtCurrent"
    OTHER_CURRENT_LIABILITIES = "OtherLiabilitiesCurrent"
    TOTAL_CURRENT_LIABILITIES = "LiabilitiesCurrent"
    LONG_TERM_DEBT = "LongTermDebtNoncurrent"
    OPERATING_LEASE_LIABILITY_NONCURRENT = "OperatingLeaseLiabilityNoncurrent"
    DEFERRED_TAX_LIABILITIES = "DeferredIncomeTaxLiabilitiesNet"
    OTHER_NONCURRENT_LIABILITIES = "OtherLiabilitiesNoncurrent"
    TOTAL_NONCURRENT_LIABILITIES = "LiabilitiesNoncurrent"
    TOTAL_LIABILITIES = "Liabilities"
    COMMON_STOCK_AND_APIC = "CommonStocksIncludingAdditionalPaidInCapital"
    RETAINED_EARNINGS = "RetainedEarningsAccumulatedDeficit"
    TREASURY_STOCK = "TreasuryStockValue"
    ACCUMULATED_OCI = "AccumulatedOtherComprehensiveIncomeLossNetOfTax"
    TOTAL_STOCKHOLDERS_EQUITY = "StockholdersEquity"
    MINORITY_INTEREST = "MinorityInterest"
    TOTAL_EQUITY_INCL_MINORITY = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    TOTAL_LIABILITIES_AND_EQUITY = "LiabilitiesAndStockholdersEquity"

    # ---- Cash flow --------------------------------------------------------
    DEPRECIATION_AND_AMORTIZATION = "DepreciationDepletionAndAmortization"
    STOCK_BASED_COMPENSATION = "ShareBasedCompensation"
    DEFERRED_INCOME_TAXES = "DeferredIncomeTaxExpenseBenefit"
    CHANGE_IN_RECEIVABLES = "IncreaseDecreaseInAccountsReceivable"
    CHANGE_IN_INVENTORY = "IncreaseDecreaseInInventories"
    CHANGE_IN_PAYABLES = "IncreaseDecreaseInAccountsPayable"
    CHANGE_IN_DEFERRED_REVENUE = "IncreaseDecreaseInContractWithCustomerLiability"
    OTHER_OPERATING_ACTIVITIES = "OtherOperatingActivitiesCashFlowStatement"
    NET_CASH_OPERATING = "NetCashProvidedByUsedInOperatingActivities"
    CAPITAL_EXPENDITURES = "PaymentsToAcquirePropertyPlantAndEquipment"
    ACQUISITIONS_NET_OF_CASH = "PaymentsToAcquireBusinessesNetOfCashAcquired"
    PURCHASES_OF_INVESTMENTS = "PaymentsToAcquireInvestments"
    SALES_MATURITIES_OF_INVESTMENTS = "ProceedsFromSaleMaturityAndCollectionsOfInvestments"
    OTHER_INVESTING_ACTIVITIES = "PaymentsForProceedsFromOtherInvestingActivities"
    NET_CASH_INVESTING = "NetCashProvidedByUsedInInvestingActivities"
    DEBT_ISSUED = "ProceedsFromIssuanceOfDebt"
    DEBT_REPAID = "RepaymentsOfDebt"
    SHARE_REPURCHASES = "PaymentsForRepurchaseOfCommonStock"
    DIVIDENDS_PAID = "PaymentsOfDividends"
    OTHER_FINANCING_ACTIVITIES = "ProceedsFromPaymentsForOtherFinancingActivities"
    NET_CASH_FINANCING = "NetCashProvidedByUsedInFinancingActivities"
    FX_EFFECT_ON_CASH = "EffectOfExchangeRateOnCashAndCashEquivalents"
    NET_CHANGE_IN_CASH = "CashAndCashEquivalentsPeriodIncreaseDecrease"
    CASH_BEGINNING_OF_PERIOD = "CashAndCashEquivalentsAtCarryingValueBeginningOfPeriod"
    CASH_END_OF_PERIOD = "CashAndCashEquivalentsAtCarryingValueEndOfPeriod"


@dataclass(frozen=True, slots=True)
class ConceptMeta:
    """Static metadata describing how a concept behaves."""

    statement: Statement
    period_kind: PeriodKind
    sign: SignConvention
    unit: Unit
    label: str
    #: True when the concept is a subtotal derivable from other concepts. Subtotals
    #: are recomputed by the validation layer rather than trusted on extraction.
    is_subtotal: bool = False
    #: How deeply the line is indented when rendered. 0 is a top-level line or
    #: subtotal; 1 is a component rolling up into the subtotal below it.
    indent: int = 0


_M = SignConvention.MAGNITUDE
_R = SignConvention.AS_REPORTED
_I = PeriodKind.INSTANT
_D = PeriodKind.DURATION
_IS = Statement.INCOME_STATEMENT
_BS = Statement.BALANCE_SHEET
_CF = Statement.CASH_FLOW


CONCEPT_META: dict[Concept, ConceptMeta] = {
    # ---- Income statement -------------------------------------------------
    Concept.REVENUE: ConceptMeta(_IS, _D, _M, Unit.USD, "Revenue"),
    Concept.COST_OF_REVENUE: ConceptMeta(_IS, _D, _M, Unit.USD, "Cost of revenue"),
    Concept.GROSS_PROFIT: ConceptMeta(_IS, _D, _R, Unit.USD, "Gross profit", is_subtotal=True),
    Concept.RESEARCH_AND_DEVELOPMENT: ConceptMeta(_IS, _D, _M, Unit.USD, "Research and development"),
    Concept.SELLING_GENERAL_ADMIN: ConceptMeta(_IS, _D, _M, Unit.USD, "Selling, general and administrative"),
    Concept.SALES_AND_MARKETING: ConceptMeta(_IS, _D, _M, Unit.USD, "Sales and marketing"),
    Concept.GENERAL_AND_ADMIN: ConceptMeta(_IS, _D, _M, Unit.USD, "General and administrative"),
    Concept.OTHER_OPERATING_EXPENSE: ConceptMeta(_IS, _D, _M, Unit.USD, "Other operating expense"),
    Concept.TOTAL_OPERATING_EXPENSES: ConceptMeta(_IS, _D, _M, Unit.USD, "Total operating expenses", is_subtotal=True),
    Concept.OPERATING_INCOME: ConceptMeta(_IS, _D, _R, Unit.USD, "Operating income", is_subtotal=True),
    Concept.INTEREST_EXPENSE: ConceptMeta(_IS, _D, _M, Unit.USD, "Interest expense"),
    Concept.INTEREST_INCOME: ConceptMeta(_IS, _D, _M, Unit.USD, "Interest income"),
    Concept.OTHER_NONOPERATING_INCOME: ConceptMeta(_IS, _D, _R, Unit.USD, "Other non-operating income"),
    Concept.PRETAX_INCOME: ConceptMeta(_IS, _D, _R, Unit.USD, "Income before income taxes", is_subtotal=True),
    Concept.INCOME_TAX_EXPENSE: ConceptMeta(_IS, _D, _R, Unit.USD, "Income tax expense"),
    Concept.NET_INCOME_INCLUDING_NCI: ConceptMeta(_IS, _D, _R, Unit.USD, "Net income including non-controlling interests", is_subtotal=True),
    Concept.NET_INCOME_TO_NCI: ConceptMeta(_IS, _D, _R, Unit.USD, "Net income attributable to non-controlling interests"),
    Concept.NET_INCOME: ConceptMeta(_IS, _D, _R, Unit.USD, "Net income", is_subtotal=True),
    Concept.NET_INCOME_TO_COMMON: ConceptMeta(_IS, _D, _R, Unit.USD, "Net income to common"),
    Concept.EPS_BASIC: ConceptMeta(_IS, _D, _R, Unit.USD_PER_SHARE, "Basic EPS"),
    Concept.EPS_DILUTED: ConceptMeta(_IS, _D, _R, Unit.USD_PER_SHARE, "Diluted EPS"),
    Concept.SHARES_BASIC: ConceptMeta(_IS, _D, _M, Unit.SHARES, "Weighted average shares, basic"),
    Concept.SHARES_DILUTED: ConceptMeta(_IS, _D, _M, Unit.SHARES, "Weighted average shares, diluted"),

    # ---- Balance sheet: assets -------------------------------------------
    Concept.CASH_AND_EQUIVALENTS: ConceptMeta(_BS, _I, _M, Unit.USD, "Cash and cash equivalents"),
    Concept.SHORT_TERM_INVESTMENTS: ConceptMeta(_BS, _I, _M, Unit.USD, "Short-term investments"),
    Concept.ACCOUNTS_RECEIVABLE: ConceptMeta(_BS, _I, _M, Unit.USD, "Accounts receivable, net"),
    Concept.INVENTORY: ConceptMeta(_BS, _I, _M, Unit.USD, "Inventory"),
    Concept.PREPAID_EXPENSES: ConceptMeta(_BS, _I, _M, Unit.USD, "Prepaid expenses"),
    Concept.OTHER_CURRENT_ASSETS: ConceptMeta(_BS, _I, _M, Unit.USD, "Other current assets"),
    Concept.TOTAL_CURRENT_ASSETS: ConceptMeta(_BS, _I, _M, Unit.USD, "Total current assets", is_subtotal=True),
    Concept.PROPERTY_PLANT_EQUIPMENT_NET: ConceptMeta(_BS, _I, _M, Unit.USD, "Property and equipment, net"),
    Concept.LONG_TERM_INVESTMENTS: ConceptMeta(_BS, _I, _M, Unit.USD, "Long-term investments"),
    Concept.GOODWILL: ConceptMeta(_BS, _I, _M, Unit.USD, "Goodwill"),
    Concept.INTANGIBLE_ASSETS: ConceptMeta(_BS, _I, _M, Unit.USD, "Intangible assets, net"),
    Concept.OPERATING_LEASE_ROU_ASSET: ConceptMeta(_BS, _I, _M, Unit.USD, "Operating lease right-of-use assets"),
    Concept.OTHER_NONCURRENT_ASSETS: ConceptMeta(_BS, _I, _M, Unit.USD, "Other non-current assets"),
    Concept.TOTAL_NONCURRENT_ASSETS: ConceptMeta(_BS, _I, _M, Unit.USD, "Total non-current assets", is_subtotal=True),
    Concept.TOTAL_ASSETS: ConceptMeta(_BS, _I, _M, Unit.USD, "Total assets", is_subtotal=True),

    # ---- Balance sheet: liabilities & equity ------------------------------
    Concept.ACCOUNTS_PAYABLE: ConceptMeta(_BS, _I, _M, Unit.USD, "Accounts payable"),
    Concept.ACCRUED_LIABILITIES: ConceptMeta(_BS, _I, _M, Unit.USD, "Accrued liabilities"),
    Concept.DEFERRED_REVENUE_CURRENT: ConceptMeta(_BS, _I, _M, Unit.USD, "Deferred revenue, current"),
    Concept.SHORT_TERM_DEBT: ConceptMeta(_BS, _I, _M, Unit.USD, "Short-term debt"),
    Concept.CURRENT_PORTION_LONG_TERM_DEBT: ConceptMeta(_BS, _I, _M, Unit.USD, "Current portion of long-term debt"),
    Concept.OTHER_CURRENT_LIABILITIES: ConceptMeta(_BS, _I, _M, Unit.USD, "Other current liabilities"),
    Concept.TOTAL_CURRENT_LIABILITIES: ConceptMeta(_BS, _I, _M, Unit.USD, "Total current liabilities", is_subtotal=True),
    Concept.LONG_TERM_DEBT: ConceptMeta(_BS, _I, _M, Unit.USD, "Long-term debt"),
    Concept.OPERATING_LEASE_LIABILITY_NONCURRENT: ConceptMeta(_BS, _I, _M, Unit.USD, "Operating lease liabilities, non-current"),
    Concept.DEFERRED_TAX_LIABILITIES: ConceptMeta(_BS, _I, _M, Unit.USD, "Deferred tax liabilities"),
    Concept.OTHER_NONCURRENT_LIABILITIES: ConceptMeta(_BS, _I, _M, Unit.USD, "Other non-current liabilities"),
    Concept.TOTAL_NONCURRENT_LIABILITIES: ConceptMeta(_BS, _I, _M, Unit.USD, "Total non-current liabilities", is_subtotal=True),
    Concept.TOTAL_LIABILITIES: ConceptMeta(_BS, _I, _M, Unit.USD, "Total liabilities", is_subtotal=True),
    Concept.COMMON_STOCK_AND_APIC: ConceptMeta(_BS, _I, _R, Unit.USD, "Common stock and paid-in capital"),
    Concept.RETAINED_EARNINGS: ConceptMeta(_BS, _I, _R, Unit.USD, "Retained earnings (accumulated deficit)"),
    Concept.TREASURY_STOCK: ConceptMeta(_BS, _I, _M, Unit.USD, "Treasury stock"),
    Concept.ACCUMULATED_OCI: ConceptMeta(_BS, _I, _R, Unit.USD, "Accumulated other comprehensive income (loss)"),
    Concept.TOTAL_STOCKHOLDERS_EQUITY: ConceptMeta(_BS, _I, _R, Unit.USD, "Total stockholders' equity", is_subtotal=True),
    Concept.MINORITY_INTEREST: ConceptMeta(_BS, _I, _R, Unit.USD, "Non-controlling interests"),
    Concept.TOTAL_EQUITY_INCL_MINORITY: ConceptMeta(_BS, _I, _R, Unit.USD, "Total equity including non-controlling interests", is_subtotal=True),
    Concept.TOTAL_LIABILITIES_AND_EQUITY: ConceptMeta(_BS, _I, _M, Unit.USD, "Total liabilities and equity", is_subtotal=True),

    # ---- Cash flow --------------------------------------------------------
    Concept.DEPRECIATION_AND_AMORTIZATION: ConceptMeta(_CF, _D, _M, Unit.USD, "Depreciation and amortization"),
    Concept.STOCK_BASED_COMPENSATION: ConceptMeta(_CF, _D, _M, Unit.USD, "Stock-based compensation"),
    Concept.DEFERRED_INCOME_TAXES: ConceptMeta(_CF, _D, _R, Unit.USD, "Deferred income taxes"),
    Concept.CHANGE_IN_RECEIVABLES: ConceptMeta(_CF, _D, _R, Unit.USD, "Change in accounts receivable"),
    Concept.CHANGE_IN_INVENTORY: ConceptMeta(_CF, _D, _R, Unit.USD, "Change in inventory"),
    Concept.CHANGE_IN_PAYABLES: ConceptMeta(_CF, _D, _R, Unit.USD, "Change in accounts payable"),
    Concept.CHANGE_IN_DEFERRED_REVENUE: ConceptMeta(_CF, _D, _R, Unit.USD, "Change in deferred revenue"),
    Concept.OTHER_OPERATING_ACTIVITIES: ConceptMeta(_CF, _D, _R, Unit.USD, "Other operating activities"),
    Concept.NET_CASH_OPERATING: ConceptMeta(_CF, _D, _R, Unit.USD, "Net cash from operating activities", is_subtotal=True),
    Concept.CAPITAL_EXPENDITURES: ConceptMeta(_CF, _D, _M, Unit.USD, "Capital expenditures"),
    Concept.ACQUISITIONS_NET_OF_CASH: ConceptMeta(_CF, _D, _M, Unit.USD, "Acquisitions, net of cash acquired"),
    Concept.PURCHASES_OF_INVESTMENTS: ConceptMeta(_CF, _D, _M, Unit.USD, "Purchases of investments"),
    Concept.SALES_MATURITIES_OF_INVESTMENTS: ConceptMeta(_CF, _D, _M, Unit.USD, "Sales and maturities of investments"),
    Concept.OTHER_INVESTING_ACTIVITIES: ConceptMeta(_CF, _D, _R, Unit.USD, "Other investing activities"),
    Concept.NET_CASH_INVESTING: ConceptMeta(_CF, _D, _R, Unit.USD, "Net cash from investing activities", is_subtotal=True),
    Concept.DEBT_ISSUED: ConceptMeta(_CF, _D, _M, Unit.USD, "Proceeds from debt"),
    Concept.DEBT_REPAID: ConceptMeta(_CF, _D, _M, Unit.USD, "Repayments of debt"),
    Concept.SHARE_REPURCHASES: ConceptMeta(_CF, _D, _M, Unit.USD, "Repurchases of common stock"),
    Concept.DIVIDENDS_PAID: ConceptMeta(_CF, _D, _M, Unit.USD, "Dividends paid"),
    Concept.OTHER_FINANCING_ACTIVITIES: ConceptMeta(_CF, _D, _R, Unit.USD, "Other financing activities"),
    Concept.NET_CASH_FINANCING: ConceptMeta(_CF, _D, _R, Unit.USD, "Net cash from financing activities", is_subtotal=True),
    Concept.FX_EFFECT_ON_CASH: ConceptMeta(_CF, _D, _R, Unit.USD, "Effect of exchange rates on cash"),
    Concept.NET_CHANGE_IN_CASH: ConceptMeta(_CF, _D, _R, Unit.USD, "Net change in cash", is_subtotal=True),
    Concept.CASH_BEGINNING_OF_PERIOD: ConceptMeta(_CF, _I, _M, Unit.USD, "Cash at beginning of period"),
    Concept.CASH_END_OF_PERIOD: ConceptMeta(_CF, _I, _M, Unit.USD, "Cash at end of period"),
}


#: Lines that sit flush left despite not being subtotals. Everything else that
#: is not a subtotal is a component rolling up into the subtotal beneath it, and
#: is indented one level.
#:
#: These are the exceptions because they are headline lines in their own right:
#: the top of the income statement, the below-the-line items between operating
#: income and net income, the per-share block, and the cash reconciliation
#: lines, none of which belong to a subtotal above them.
_FLUSH_LEFT: frozenset[Concept] = frozenset(
    {
        Concept.REVENUE,
        Concept.COST_OF_REVENUE,
        Concept.INTEREST_EXPENSE,
        Concept.INTEREST_INCOME,
        Concept.OTHER_NONOPERATING_INCOME,
        Concept.INCOME_TAX_EXPENSE,
        Concept.NET_INCOME_TO_NCI,
        Concept.NET_INCOME_TO_COMMON,
        Concept.EPS_BASIC,
        Concept.EPS_DILUTED,
        Concept.SHARES_BASIC,
        Concept.SHARES_DILUTED,
        Concept.FX_EFFECT_ON_CASH,
        Concept.CASH_BEGINNING_OF_PERIOD,
        Concept.CASH_END_OF_PERIOD,
    }
)

# Indentation is derived rather than declared per entry: a line is indented if
# and only if it is a component feeding a subtotal. Deriving it keeps the rule
# visible and stops the registry drifting into 85 hand-maintained integers that
# disagree with each other.
CONCEPT_META = {
    concept: (
        m
        if m.is_subtotal or concept in _FLUSH_LEFT
        else _replace(m, indent=1)
    )
    for concept, m in CONCEPT_META.items()
}


def meta(concept: Concept) -> ConceptMeta:
    """Return metadata for `concept`."""
    return CONCEPT_META[concept]


def concepts_for(statement: Statement) -> list[Concept]:
    """Return every concept belonging to `statement`, in declaration order.

    Declaration order in `CONCEPT_META` *is* the display order: the registry is
    written top-to-bottom in the order a reader expects to see the lines, so a
    statement view can render it directly without a parallel ordering table to
    keep in sync.
    """
    return [c for c, m in CONCEPT_META.items() if m.statement == statement]


def statement_layout(statement: Statement) -> list[tuple[Concept, ConceptMeta]]:
    """Concepts for `statement` in render order, with their display metadata."""
    return [(c, m) for c, m in CONCEPT_META.items() if m.statement == statement]


# Guard against the registry drifting out of sync with the enum. A concept without
# metadata would silently bypass sign normalisation and period-kind checking, so it
# is caught at import time rather than at extraction time.
_missing = set(Concept) - set(CONCEPT_META)
if _missing:  # pragma: no cover - import-time invariant
    raise RuntimeError(f"Concepts missing metadata: {sorted(c.value for c in _missing)}")
