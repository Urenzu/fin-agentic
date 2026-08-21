"""Parsing the SEC's rendered statement exhibits.

`companyfacts` gives values with no presentation: no line order, no hierarchy,
no filer labels, and no way to tell a balance sheet line from a footnote
schedule. The rendered exhibits (`R*.htm`, listed in `FilingSummary.xml`) carry
all of it, because they are the SEC's own rendering of the statement as filed.

That makes them the right source for *display*. Rendering as filed also
sidesteps the coverage problem entirely: Apple's balance sheet includes a $33bn
"Vendor non-trade receivables" line that no canonical vocabulary would think to
include, and every filer has a few such lines. A canonical view must either map
them all -- which is unbounded -- or show a total that does not add up.

The canonical ledger keeps its own job: charts, time series and cross-company
comparison, all of which need one consistent shape and cannot use as-filed rows.

Structure of an exhibit
-----------------------
    <th class="tl">   title, plus scale hints ("$ in Millions")
    <th class="th">   one per period column ("Sep. 27, 2025"), optionally under
                      a spanning cell naming the duration ("3 Months Ended")
    <tr class="ro">   data row          <tr class="rou">  underlined = a total
    <td class="pl">   label, with the element name in an onclick handler
    <td class="nump"> positive number   <td class="num">  parenthesised negative
    <td class="text"> empty cell

Indentation is not encoded in the markup -- there is no padding-left to read.
Hierarchy comes from `*Abstract` elements, which are section headings ("Current
assets:") that open a level, and from underlined total rows that close one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

SCALE_WORDS: dict[str, Decimal] = {
    "thousands": Decimal(1_000),
    "millions": Decimal(1_000_000),
    "billions": Decimal(1_000_000_000),
}

#: Element-name fragments marking a per-share amount. These are printed at full
#: precision and must never take the statement's monetary scale -- multiplying
#: EPS by a million produces a number that is wrong by six orders of magnitude
#: while still looking like a plausible figure.
_PER_SHARE_MARKERS = ("PerShare", "PerBasicShare", "PerDilutedShare")


@dataclass(frozen=True, slots=True)
class AsFiledRow:
    """One line of a statement, as the filer presented it."""

    label: str
    #: Element name, e.g. "us-gaap_Assets" or a company extension. None when the
    #: renderer emitted no reference.
    element: str | None
    #: Section heading rather than a value-bearing line.
    is_abstract: bool
    #: Underlined in the rendering, i.e. a subtotal or total.
    is_total: bool
    indent: int
    #: Keyed by `AsFiledColumn.key`. A missing key means the cell was blank,
    #: which is how the filer indicates the line does not apply to that period.
    values: dict[str, Decimal]

    @property
    def is_us_gaap(self) -> bool:
        return bool(self.element and self.element.startswith("us-gaap_"))

    @property
    def tag(self) -> str | None:
        """The bare element name, without its taxonomy prefix."""
        if not self.element:
            return None
        _, _, name = self.element.partition("_")
        return name or None


@dataclass(frozen=True, slots=True)
class AsFiledColumn:
    """One period column of a statement.

    A quarterly statement of operations carries the same period *end* twice --
    once under "3 Months Ended" and once under "9 Months Ended" -- so the
    printed date does not identify a column. `key` does, and is what
    `AsFiledRow.values` is keyed by.

    The key is the column's ordinal position rather than anything derived from
    the heading, because position is the only property the renderer guarantees
    to be unique. Keying by the date silently collapsed the year-to-date
    figures onto the quarterly ones, leaving a statement whose every number
    looked plausible and was the wrong period.
    """

    key: str
    #: The period end as the filer printed it, e.g. "Jun. 27, 2026".
    label: str
    #: The spanning heading this column sat under, e.g. "3 Months Ended".
    #: None for an instant, which is how balance sheet columns arrive.
    duration: str | None
    date: date | None


@dataclass(frozen=True, slots=True)
class AsFiledStatement:
    """A statement exactly as the filer presented it."""

    title: str
    #: Column headings in the order rendered, most recent first as the SEC
    #: renders them.
    columns: tuple[AsFiledColumn, ...]
    rows: tuple[AsFiledRow, ...]
    monetary_scale: Decimal = Decimal(1)
    share_scale: Decimal = Decimal(1)

    @property
    def line_count(self) -> int:
        return sum(1 for r in self.rows if not r.is_abstract)

    @property
    def display_name(self) -> str:
        """The statement's name, without the trailing units annotation.

        Preferred over `FilingSummary.xml`'s ShortName, which the SEC's renderer
        sometimes emits with non-ASCII characters already replaced by question
        marks -- Chipotle's "SHAREHOLDERS' EQUITY" arrives as "SHAREHOLDERS???
        EQUITY". The exhibit itself carries the correct HTML entity, so taking
        the title from here avoids inheriting that corruption.
        """
        name = self.title
        for separator in (" - USD", " - $", " ("):
            index = name.find(separator)
            if index > 0:
                name = name[:index]
        return name.strip()

    def row_for(self, tag: str) -> AsFiledRow | None:
        return next((r for r in self.rows if r.tag == tag), None)


def parse_statement(html: str) -> AsFiledStatement:
    """Parse one rendered exhibit into structured rows."""
    title_raw = _first(r'<th class="tl"[^>]*>(.*?)</th>', html)
    title_text = _text(title_raw or "")
    monetary_scale, share_scale = _scales(title_text)

    columns = tuple(
        AsFiledColumn(key=str(index), label=label, duration=duration, date=_parse_date(label))
        for index, (label, duration) in enumerate(_period_columns(html))
    )

    rows: list[AsFiledRow] = []
    depth = 0

    for row_html in re.findall(r"<tr[^>]*>.*?</tr>", html, re.S):
        row_class = _first(r'<tr class="([^"]+)"', row_html) or ""
        cells = re.findall(r"<td[^>]*class=\"([a-z]+)\"[^>]*>(.*?)</td>", row_html, re.S)
        if not cells:
            continue

        label_cell = next((body for cls, body in cells if cls == "pl"), None)
        if label_cell is None:
            continue

        label = _text(label_cell)
        if not label:
            continue

        element = _first(r"defref_([A-Za-z0-9_\-]+)", label_cell)
        is_abstract = bool(element and element.endswith("Abstract"))
        # The renderer underlines subtotals and totals; the trailing "u" on the
        # row class is that underline.
        is_total = row_class.endswith("u")

        if is_total and depth > 0:
            depth -= 1
        indent = depth
        if is_abstract:
            depth += 1

        values: dict[str, Decimal] = {}
        if not is_abstract:
            numeric = [(cls, body) for cls, body in cells if cls in ("num", "nump", "text")]
            scale = _scale_for(element, monetary_scale, share_scale)
            for column, (cls, body) in zip(columns, numeric, strict=False):
                if cls == "text":
                    continue
                parsed = _parse_number(_text(body))
                if parsed is not None:
                    values[column.key] = parsed * scale

        rows.append(
            AsFiledRow(
                label=label,
                element=element,
                is_abstract=is_abstract,
                is_total=is_total,
                indent=indent,
                values=values,
            )
        )

    return AsFiledStatement(
        title=title_text,
        columns=columns,
        rows=tuple(rows),
        monetary_scale=monetary_scale,
        share_scale=share_scale,
    )


def _period_columns(html: str) -> list[tuple[str, str | None]]:
    """The period columns, as (date, duration) pairs.

    Statements covering durations carry a two-row header: spanning cells
    reading "12 Months Ended" above the individual period dates. A spanning
    cell is not a column of its own -- counting it as one shifts every value a
    column to the left, silently mis-attributing an entire statement to the
    wrong periods.

    It is not noise either. A 10-Q prints two blocks side by side, "3 Months
    Ended" and "9 Months Ended", and both carry the same period end date, so
    the spanning cell is the only thing distinguishing the quarter from the
    year to date. Its `colspan` says how many of the dates below belong to it.
    """
    spans: list[tuple[str, int]] = []
    dates: list[str] = []

    for attrs, body in re.findall(r'<th class="th"([^>]*)>(.*?)</th>', html, re.S):
        text = _text(body)
        if not text:
            continue
        colspan = re.search(r'colspan="(\d+)"', attrs)
        width = int(colspan.group(1)) if colspan is not None else 1
        if width > 1:
            spans.append((text, width))
        else:
            dates.append(text)

    # Flattened in order, so the nth date takes the heading whose run covers
    # position n. A statement of instants has no spans and every column is
    # left undated in duration terms, which is exactly right for a balance
    # sheet. A single span covering everything ("12 Months Ended") labels all
    # of them the same, which is also right.
    durations: list[str | None] = []
    for text, width in spans:
        durations.extend([text] * width)

    return [
        (label, durations[index] if index < len(durations) else None)
        for index, label in enumerate(dates)
    ]


def _scale_for(element: str | None, monetary: Decimal, shares: Decimal) -> Decimal:
    """The multiplier that applies to a row's printed values."""
    if element is None:
        return monetary
    if any(marker in element for marker in _PER_SHARE_MARKERS):
        return Decimal(1)
    if "Shares" in element or "shares" in element:
        return shares
    return monetary


def _scales(title: str) -> tuple[Decimal, Decimal]:
    """Read the monetary and share multipliers from a statement title.

    Titles look like "CONSOLIDATED BALANCE SHEETS - USD ($) shares in Thousands,
    $ in Millions", so the two scales are stated separately and must be read
    separately -- share counts and dollars are frequently at different scales in
    the same statement.
    """
    lowered = title.lower()
    monetary = Decimal(1)
    shares = Decimal(1)

    for match in re.finditer(r"(\$|shares)\s+in\s+(thousands|millions|billions)", lowered):
        subject, word = match.group(1), match.group(2)
        if subject == "$":
            monetary = SCALE_WORDS[word]
        else:
            shares = SCALE_WORDS[word]

    # "in Millions" with no subject applies to the monetary amounts.
    if monetary == Decimal(1):
        bare = re.search(r"in\s+(thousands|millions|billions)", lowered)
        if bare:
            monetary = SCALE_WORDS[bare.group(1)]
    return monetary, shares


def _parse_number(text: str) -> Decimal | None:
    """Parse a rendered cell, honouring accounting parentheses for negatives."""
    cleaned = text.replace("$", "").replace(",", "").replace("\xa0", "").strip()
    if not cleaned or cleaned in ("&#160;", "-", "—"):
        return None

    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    cleaned = cleaned.rstrip("%").strip()
    if not cleaned:
        return None

    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
    return -value if negative else value


_DATE_FORMATS = ("%b. %d, %Y", "%b %d, %Y", "%B %d, %Y")


def _parse_date(text: str) -> date | None:
    candidate = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None


def _first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.S)
    return match.group(1) if match else None


def _text(html: str) -> str:
    """Strip markup and normalise whitespace."""
    from html import unescape

    stripped = re.sub(r"<br\s*/?>", " ", html)
    stripped = re.sub(r"<[^>]+>", "", stripped)
    return re.sub(r"\s+", " ", unescape(stripped)).strip()
