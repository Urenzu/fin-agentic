/**
 * Shortening a statement's name for the panel header.
 *
 * Filers title their statements in full: "CONDENSED CONSOLIDATED STATEMENTS OF
 * COMPREHENSIVE INCOME". Across a row of five panels the first four words are
 * the same four words every time, so the part that distinguishes one statement
 * from the next arrives last and reads smallest. Dropping the shared preamble
 * puts "COMPREHENSIVE INCOME" where the eye already is.
 *
 * Nothing is lost. "Consolidated" is true of every statement on the board --
 * these are the primary financial statements of a single registrant, not
 * segment or parent-only schedules -- and "condensed" is what a 10-Q is, which
 * the panel already states beside the filing date. The full name stays on the
 * header's tooltip.
 */

/**
 * Leading words that describe the *presentation* rather than the statement.
 *
 * Stripped only from the front, and only while every word so far has been one
 * of these, so "CONSOLIDATED STATEMENTS OF OPERATIONS AND COMPREHENSIVE
 * INCOME" keeps everything from "OPERATIONS" onward.
 */
const QUALIFIERS = new Set([
  "CONDENSED",
  "CONSOLIDATED",
  "CONSOLIDATING",
  "COMBINED",
  "INTERIM",
  "UNAUDITED",
  "AND",
]);

/** The connective between the qualifiers and the subject. */
const LEAD_IN = /^statements? of\b\s*/i;

export function statementTitle(name: string): string {
  const trimmed = name.trim();
  if (trimmed === "") return name;

  const words = trimmed.split(/\s+/);
  let start = 0;
  while (start < words.length && QUALIFIERS.has((words[start] ?? "").toUpperCase())) {
    start += 1;
  }

  const rest = words.slice(start).join(" ").replace(LEAD_IN, "").trim();

  // A name that is nothing but qualifiers and a lead-in has no subject to
  // shorten to, and is better shown in full than shown blank.
  return rest === "" ? trimmed : rest;
}
