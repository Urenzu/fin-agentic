import type { Coverage } from "./types";

/**
 * What the card can honestly say about a ledger.
 *
 * It used to say "Corroborated 48%", from `verified_count / fact_count`. That
 * number reads as an accuracy score and is not one. A fact is counted verified
 * when it takes part in a satisfied accounting identity, so a figure no
 * identity happens to cover stays unverified however correct it is -- the
 * ratio could never reach 100%, and its distance from 100% said nothing about
 * whether anything was wrong. Shown beside "Facts 3,867" it invited exactly
 * the reading it could not support.
 *
 * Two questions were tangled in it, and they separate cleanly:
 *
 *   `holds`     of the identities that could be evaluated, how many hold.
 *               The trust signal, and the one that should be near 100%.
 *   `evaluated` of all the identities, how many had the data to run at all.
 *               The coverage signal, and today it is around half.
 *
 * Reporting them apart is what makes either meaningful: a ledger where every
 * check passes because almost none could run is not the same as one where
 * every check passes because they all ran, and the old number gave both the
 * same score.
 */
export type Assurance = {
  /** Identities evaluated: passed + failed. */
  evaluated: number;
  /** Identities that could not run because a concept was missing. */
  skipped: number;
  /** Every identity considered. */
  total: number;
  /** passed / evaluated, or null when nothing could be evaluated. */
  holds: number | null;
  /** evaluated / total, or null when there are no identities at all. */
  coverage: number | null;
  failed: number;
};

export function assuranceOf(coverage: Coverage): Assurance {
  const evaluated = coverage.checks_passed + coverage.checks_failed;
  const total = evaluated + coverage.checks_skipped;

  return {
    evaluated,
    skipped: coverage.checks_skipped,
    total,
    // Null rather than 0 or 100: with nothing evaluated there is no answer,
    // and either number would be a claim.
    holds: evaluated > 0 ? coverage.checks_passed / evaluated : null,
    coverage: total > 0 ? evaluated / total : null,
    failed: coverage.checks_failed,
  };
}

/** A share as a percentage, or an em dash when there is no answer. */
export function percent(share: number | null): string {
  return share === null ? "—" : `${Math.round(share * 100)}%`;
}

/**
 * How many identities hold, written as the counts rather than a share.
 *
 * A percentage lies here at exactly the moment it matters. Apple has three
 * breaks in 913 evaluated identities; 910/913 rounds to 100%, so the card
 * showed a clean 100% while three things were in fact broken. Rounding down
 * would be worse -- a filer with no breaks at all would read as 99%. The
 * counts have neither problem and are no harder to take in.
 */
export function holdsLabel(assurance: Assurance): string {
  if (assurance.evaluated === 0) return "—";
  return `${assurance.evaluated - assurance.failed} / ${assurance.evaluated}`;
}

/**
 * One line saying what the numbers mean, for the card's tooltip.
 *
 * Spelled out because the counts alone are ambiguous: "1,247 checks" could be
 * a lot or a little, and only the sentence says which part is the ledger's
 * limitation rather than the filer's.
 */
export function assuranceHint(assurance: Assurance, factCount?: number): string {
  const { evaluated, total, failed, skipped } = assurance;
  if (total === 0) return "No accounting identities were evaluated.";

  const held = `${evaluated - failed} of ${evaluated} evaluated identities hold`;
  const rest =
    skipped === 0
      ? "every identity had the data to run."
      : `${skipped} more could not run because the ledger is missing a concept they need.`;
  const size = factCount === undefined ? "" : ` Ledger holds ${factCount.toLocaleString()} facts.`;
  return `${held}; ${rest}${size}`;
}
