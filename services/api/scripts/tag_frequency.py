"""Measure which us-gaap tags actually matter, and how much of the data we cover.

The us-gaap taxonomy has on the order of 18,000 elements, which sounds like an
impossible surface to cover by hand. It is not, for two reasons this script
quantifies:

1. Usage follows a steep power law. A small number of tags account for the
   overwhelming majority of reported facts, because every filer reports total
   assets and almost none report the exotic tail.
2. `companyfacts` returns only the standard `us-gaap` and `dei` taxonomies --
   company-specific extension elements do not appear. The vocabulary is
   therefore closed, unlike the raw filings where extensions are unbounded.

So the map does not need 18,000 entries. It needs the head of the distribution,
and this script says exactly where that head ends.

Run:  python scripts/tag_frequency.py [--tickers N]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finagentic.ingest.edgar import EdgarClient, EdgarError
from finagentic.ingest.tag_map import TAG_TO_CONCEPT

#: A deliberately cross-sector sample. Coverage measured only on large-cap tech
#: would look far better than it is, because those filers share a house style.
SAMPLE_TICKERS = [
    # tech
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "CRM", "ORCL", "ADBE",
    # retail / consumer
    "WMT", "COST", "TGT", "KO", "PEP", "PG", "MCD", "NKE",
    # industrial / energy
    "CAT", "BA", "GE", "LMT", "CVX", "COP", "UNP",
    # healthcare
    "JNJ", "PFE", "UNH", "ABBV", "TMO",
    # financials (different Reg S-X article -- expected to fit poorly)
    "JPM", "BAC", "GS", "AXP", "BRK-B",
    # telecom / utilities / REIT
    "VZ", "T", "NEE", "DUK", "AMT", "PLD",
    # autos / airlines
    "TSLA", "F", "GM", "DAL",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", type=int, default=len(SAMPLE_TICKERS))
    parser.add_argument("--cache", type=Path, default=Path(".edgar_cache"))
    args = parser.parse_args()

    client = EdgarClient(cache_dir=args.cache)

    # Two different questions, so two counters: how often a tag is used at all,
    # and how many distinct companies use it. A tag used heavily by one filer
    # matters far less than one used lightly by all of them.
    instances: Counter[str] = Counter()
    companies: Counter[str] = Counter()
    failed: list[str] = []

    tickers = SAMPLE_TICKERS[: args.tickers]
    for i, ticker in enumerate(tickers, 1):
        try:
            registrant = client.lookup(ticker)
            payload = client.company_facts(registrant)
        except EdgarError as exc:
            failed.append(f"{ticker}: {exc}")
            continue

        gaap = payload.get("facts", {}).get("us-gaap", {})
        for tag, body in gaap.items():
            n = sum(len(rows) for rows in body.get("units", {}).values())
            instances[tag] += n
            companies[tag] += 1
        print(f"  [{i}/{len(tickers)}] {ticker:6s} {len(gaap):4d} tags", flush=True)

    if not instances:
        print("no data fetched")
        return 1

    total_instances = sum(instances.values())
    mapped = set(TAG_TO_CONCEPT)

    print(f"\n{'=' * 72}")
    print(f"{len(tickers) - len(failed)} companies, {len(instances)} distinct tags, "
          f"{total_instances:,} fact instances")
    if failed:
        print(f"failed: {'; '.join(failed)}")

    # How many tags to reach a given share of all reported facts.
    print(f"\n{'-' * 72}")
    print("Tags needed to cover a share of all fact instances:")
    ranked = instances.most_common()
    cumulative = 0
    thresholds = [0.50, 0.75, 0.90, 0.95, 0.99]
    ti = 0
    for rank, (_, count) in enumerate(ranked, 1):
        cumulative += count
        while ti < len(thresholds) and cumulative / total_instances >= thresholds[ti]:
            print(f"   {thresholds[ti]:5.0%}  ->  {rank:5d} tags")
            ti += 1

    covered = sum(instances[t] for t in mapped if t in instances)
    print(f"\n{'-' * 72}")
    print(f"Our map has {len(mapped)} tags and covers "
          f"{covered / total_instances:.1%} of fact instances")

    # The actionable output: frequent tags we do not yet map. Sorted by how many
    # companies use them, since breadth of use matters more than raw volume.
    print(f"\n{'-' * 72}")
    print("Top unmapped tags, by number of companies reporting them:")
    print(f"{'tag':<70s} {'cos':>4s} {'instances':>10s}")
    shown = 0
    for tag, n_companies in companies.most_common():
        if tag in mapped:
            continue
        print(f"{tag:<70s} {n_companies:>4d} {instances[tag]:>10,d}")
        shown += 1
        if shown >= 40:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
