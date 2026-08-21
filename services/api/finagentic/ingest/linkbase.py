"""The filer's own arithmetic, as published with the filing.

Every XBRL filing ships a *calculation linkbase* -- `<ticker>-<date>_cal.xml`,
listed in `FilingSummary.xml` alongside the rendered exhibits. It states, in
machine-readable form and with explicit signs, every subtotal relationship the
filer asserts:

    NetIncomeLoss  =  IncomeLossFromContinuingOperationsBeforeTax  (+1)
                   +  IncomeTaxExpenseBenefit                      (-1)

Apple's FY2025 10-K publishes 213 of these.

Why this is the right source
----------------------------
It answers, per filing, the question a concept vocabulary was being built to
answer, and answers it better. There is no matching: the arcs name the filer's
own elements, which are the same elements the rendered exhibit carries. There
is no drift over time, because each filing brings its own. And the denominator
belongs to the filer -- "213 of 213 relationships hold" is a claim we cannot
flatter by deciding a tag does not count, which is exactly what went wrong with
a coverage ratio we defined ourselves.

What it does not give
---------------------
Only what the filer chose to assert. If a filer publishes no arc for
`GrossProfit = Revenue - CostOfRevenue`, that relationship is unchecked here.
Verifying a filing against this is proof of internal consistency with the
filer's own stated arithmetic, which is a real and useful claim, and a narrower
one than "these numbers are correct".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

#: `<link:loc xlink:label="loc_us-gaap_Assets_abc123"
#:            xlink:href="...us-gaap-2025.xsd#us-gaap_Assets"/>`
#: The label is the local handle an arc refers to; the href fragment is the
#: element it stands for. Both are needed: arcs speak in labels, statements in
#: element names.
_LOC = re.compile(
    r'<link:loc\b[^>]*?xlink:label="([^"]+)"[^>]*?xlink:href="[^"#]*#([^"]+)"|'
    r'<link:loc\b[^>]*?xlink:href="[^"#]*#([^"]+)"[^>]*?xlink:label="([^"]+)"',
    re.S,
)

_ARC = re.compile(
    r'<link:calculationArc\b[^>]*?xlink:from="([^"]+)"[^>]*?xlink:to="([^"]+)"[^>]*?>',
    re.S,
)
_WEIGHT = re.compile(r'weight="(-?[\d.]+)"')
_ORDER = re.compile(r'order="(-?[\d.]+)"')

#: One `<link:calculationLink>` per statement or note. Splitting on them keeps
#: an element's children separate per statement: `Assets` rolls up differently
#: on the balance sheet than in a property, plant and equipment note.
_LINK = re.compile(
    r'<link:calculationLink\b[^>]*?xlink:role="([^"]+)"[^>]*?>(.*?)</link:calculationLink>',
    re.S,
)


@dataclass(frozen=True, slots=True)
class Component:
    """One term of a relationship: an element and the sign it enters with."""

    element: str
    weight: Decimal


@dataclass(frozen=True, slots=True)
class Relationship:
    """`total = sum(component.element * component.weight)`, as the filer says.

    `role` is the filer's own URI for the statement or note this belongs to,
    e.g. `http://www.apple.com/role/CONSOLIDATEDBALANCESHEETS`.
    """

    role: str
    total: str
    components: tuple[Component, ...]

    @property
    def statement_name(self) -> str:
        """The trailing segment of the role, which names the statement."""
        return self.role.rsplit("/", 1)[-1]

    def __len__(self) -> int:
        return len(self.components)


def parse_calculation_linkbase(xml: str) -> list[Relationship]:
    """Every relationship the linkbase asserts, in document order.

    Grouped by role and then by total, so each `Relationship` is one complete
    sum rather than a loose edge. A total with a single component is kept: some
    are genuine one-line roll-ups, and dropping them would quietly shrink the
    denominator we are about to report as a completeness measure.
    """
    relationships: list[Relationship] = []

    for role, body in _LINK.findall(xml):
        elements = _locators(body)
        grouped: dict[str, list[tuple[Decimal, Decimal, str]]] = {}

        for match in _ARC.finditer(body):
            parent_label, child_label = match.group(1), match.group(2)
            parent, child = elements.get(parent_label), elements.get(child_label)
            if parent is None or child is None:
                # An arc naming a locator this link does not declare is
                # malformed; skipping it is better than inventing an element.
                continue

            arc = match.group(0)
            weight_match = _WEIGHT.search(arc)
            # A summation arc without a weight is meaningless, and assuming +1
            # would silently invent a relationship the filer did not state.
            if weight_match is None:
                continue
            order_match = _ORDER.search(arc)
            order = Decimal(order_match.group(1)) if order_match else Decimal(0)
            grouped.setdefault(parent, []).append(
                (order, Decimal(weight_match.group(1)), child)
            )

        for total, rows in grouped.items():
            # `order` is the filer's own presentation order, which is the order
            # the components appear on the statement.
            rows.sort(key=lambda row: row[0])
            relationships.append(
                Relationship(
                    role=role,
                    total=total,
                    components=tuple(Component(element=e, weight=w) for _, w, e in rows),
                )
            )

    return relationships


def _locators(body: str) -> dict[str, str]:
    """Map each local label to the element it stands for."""
    found: dict[str, str] = {}
    for label_a, element_a, element_b, label_b in _LOC.findall(body):
        label = label_a or label_b
        element = element_a or element_b
        if label and element:
            found[label] = element
    return found


def calculation_filename(filing_summary: str) -> str | None:
    """The calculation linkbase named in `FilingSummary.xml`.

    Read from the summary rather than by listing the filing directory, because
    the summary is already fetched to find the exhibits -- so the linkbase
    costs no extra round trip to discover.
    """
    for name in re.findall(r"<File[^>]*>([^<]+)</File>", filing_summary):
        if name.endswith("_cal.xml"):
            return name.strip()
    return None


__all__ = [
    "Component",
    "Relationship",
    "calculation_filename",
    "parse_calculation_linkbase",
]
