import assert from "node:assert/strict";
import test from "node:test";

import { abbreviate, formatValue, parseDec, scaleExponent, trim } from "./decimal";

// ---------------------------------------------------------------------------
// scale
// ---------------------------------------------------------------------------

test("a scale string becomes its power of ten", () => {
  assert.equal(scaleExponent("1000000"), 6);
  assert.equal(scaleExponent("1000"), 3);
  assert.equal(scaleExponent("1"), 0);
});

test("a scale that is not a power of ten leaves the value unscaled", () => {
  // Better to show a figure at full precision than to shift it by a guess.
  assert.equal(scaleExponent("1500"), 0);
});

test("a value is restated at the scale the filing printed", () => {
  assert.equal(formatValue("416161000000", 6), "416,161");
});

// ---------------------------------------------------------------------------
// precision
// ---------------------------------------------------------------------------

test("no value passes through a float", () => {
  // 2^53 + 1. Number() rounds this to ...992; the point of the string wire
  // format is that it survives.
  assert.equal(formatValue("9007199254740993", 0), "9,007,199,254,740,993");
});

test("restating does not manufacture trailing zeros", () => {
  // Shifting the point left by six leaves six zeros behind it that the filing
  // never printed -- the bug this module's `trim` exists to prevent.
  assert.equal(formatValue("391035000000", 6), "391,035");
});

test("significant decimals survive trimming", () => {
  assert.equal(formatValue("7.46", 0), "7.46");
  assert.equal(formatValue("1234.50", 0), "1,234.5");
});

test("trim removes only zeros", () => {
  const parsed = parseDec("100.100");
  assert.ok(parsed);
  assert.equal(trim(parsed).exp, 1);
});

test("a decimal scale is exact where a float would drift", () => {
  // 0.1 + 0.2 territory: the classic case for keeping money off doubles.
  assert.equal(formatValue("3", 1), "0.3");
});

// ---------------------------------------------------------------------------
// presentation
// ---------------------------------------------------------------------------

test("negatives render in accounting parentheses", () => {
  assert.equal(formatValue("-14264000000", 6, { parens: true }), "(14,264)");
  assert.equal(formatValue("-14264000000", 6), "-14,264");
});

test("thousands are grouped", () => {
  assert.equal(formatValue("4424900000000", 6), "4,424,900");
});

test("rounding is half-up on the magnitude", () => {
  assert.equal(formatValue("25", 1, { dp: 0 }), "3");
  assert.equal(formatValue("-25", 1, { dp: 0 }), "-3");
});

test("per-share amounts keep two places", () => {
  assert.equal(formatValue("7.4", 0, { dp: 2 }), "7.40");
});

test("abbreviation picks the right magnitude", () => {
  assert.equal(abbreviate("391035000000"), "391.0B");
  assert.equal(abbreviate("35934000000"), "35.9B");
  assert.equal(abbreviate("1500000"), "1.5M");
  assert.equal(abbreviate("-2500000000000"), "-2.5T");
  assert.equal(abbreviate("42"), "42");
  assert.equal(abbreviate("0"), "0");
});

// ---------------------------------------------------------------------------
// malformed input
// ---------------------------------------------------------------------------

test("an unparseable value is shown verbatim rather than as NaN", () => {
  assert.equal(formatValue("n/a", 6), "n/a");
  assert.equal(parseDec(""), null);
  assert.equal(parseDec("1.2.3"), null);
});
