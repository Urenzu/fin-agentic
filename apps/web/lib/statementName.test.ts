import assert from "node:assert/strict";
import { test } from "node:test";

import { statementTitle } from "./statementName";

test("the five statements of a 10-K shorten to what tells them apart", () => {
  assert.equal(statementTitle("CONSOLIDATED STATEMENTS OF OPERATIONS"), "OPERATIONS");
  assert.equal(
    statementTitle("CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME"),
    "COMPREHENSIVE INCOME",
  );
  assert.equal(statementTitle("CONSOLIDATED BALANCE SHEETS"), "BALANCE SHEETS");
  assert.equal(
    statementTitle("CONSOLIDATED STATEMENTS OF SHAREHOLDERS' EQUITY"),
    "SHAREHOLDERS' EQUITY",
  );
  assert.equal(statementTitle("CONSOLIDATED STATEMENTS OF CASH FLOWS"), "CASH FLOWS");
});

test("a 10-Q's condensed statements shorten to the same names as the 10-K's", () => {
  // The two forms then line up in the grid instead of reading as different
  // statements; "condensed" is what the 10-Q label beside the date already says.
  assert.equal(
    statementTitle("CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS"),
    statementTitle("CONSOLIDATED STATEMENTS OF OPERATIONS"),
  );
  assert.equal(statementTitle("CONDENSED CONSOLIDATED BALANCE SHEETS"), "BALANCE SHEETS");
});

test("only leading qualifiers go, never a word that names the statement", () => {
  assert.equal(
    statementTitle("CONSOLIDATED STATEMENTS OF OPERATIONS AND COMPREHENSIVE INCOME"),
    "OPERATIONS AND COMPREHENSIVE INCOME",
  );
  // "Combined" here is part of the subject, not a leading qualifier.
  assert.equal(statementTitle("CONSOLIDATED AND COMBINED STATEMENTS OF INCOME"), "INCOME");
});

test("a singular lead-in is handled too", () => {
  assert.equal(statementTitle("CONSOLIDATED STATEMENT OF CASH FLOWS"), "CASH FLOWS");
});

test("mixed case survives, and keeps the filer's own casing", () => {
  assert.equal(statementTitle("Condensed Consolidated Balance Sheets"), "Balance Sheets");
});

test("a name with nothing to strip is left alone", () => {
  assert.equal(statementTitle("BALANCE SHEETS"), "BALANCE SHEETS");
  assert.equal(statementTitle("INCOME TAXES"), "INCOME TAXES");
});

test("a name that would shorten to nothing is shown in full", () => {
  // Better an over-long header than a blank one.
  assert.equal(statementTitle("CONSOLIDATED STATEMENTS OF"), "CONSOLIDATED STATEMENTS OF");
  assert.equal(statementTitle("CONDENSED CONSOLIDATED"), "CONDENSED CONSOLIDATED");
  assert.equal(statementTitle("   "), "   ");
});

test("shortening never produces leading or trailing space", () => {
  for (const name of [
    "CONDENSED  CONSOLIDATED   STATEMENTS OF  OPERATIONS ",
    " CONSOLIDATED BALANCE SHEETS",
  ]) {
    const short = statementTitle(name);
    assert.equal(short, short.trim(), name);
  }
});
