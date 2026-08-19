/**
 * Exact decimal arithmetic on the strings the API sends.
 *
 * The API deliberately serialises money as a decimal string rather than a JSON
 * number, because `JSON.parse` turns every number into an IEEE double. Calling
 * `Number(value)` here would throw that guarantee away at the last step, so
 * everything below works on `bigint` digits with an explicit exponent and never
 * produces a float.
 *
 * A value is held as `digits * 10^-exp`, which makes rescaling a statement to
 * the units the filing printed ("$ in Millions") a change to `exp` alone.
 */

export type Dec = {
  readonly neg: boolean;
  /** Unsigned significand. */
  readonly digits: bigint;
  /** Number of digits that sit after the decimal point. */
  readonly exp: number;
};

const DECIMAL = /^(-?)(\d*)(?:\.(\d*))?$/;

export function parseDec(value: string): Dec | null {
  const match = DECIMAL.exec(value.trim());
  if (!match) return null;

  const [, sign, whole = "", frac = ""] = match;
  if (!whole && !frac) return null;

  return {
    neg: sign === "-",
    digits: BigInt((whole || "0") + frac),
    exp: frac.length,
  };
}

export function isZero(d: Dec): boolean {
  return d.digits === 0n;
}

export function isNegative(d: Dec): boolean {
  return d.neg && d.digits !== 0n;
}

/**
 * Divide by `10^places`, i.e. restate 391_035_000_000 as 391_035 at millions.
 * Purely a change of exponent, so no digits are lost and nothing is rounded.
 */
export function shift(d: Dec, places: number): Dec {
  return { ...d, exp: d.exp + places };
}

/**
 * Drop trailing zeros that carry no information: 416161.000000 -> 416161.
 *
 * Restating a value at the statement's scale is a shift of the decimal point,
 * so dividing 416,161,000,000 by a million leaves six zeros after the point
 * that the filing never printed. Exact, because only zeros are removed.
 */
export function trim(d: Dec): Dec {
  let { digits, exp } = d;
  while (exp > 0 && digits % 10n === 0n) {
    digits /= 10n;
    exp -= 1;
  }
  return { ...d, digits, exp };
}

/** Round half-up to `dp` decimal places. */
export function round(d: Dec, dp: number): Dec {
  if (d.exp === dp) return d;

  if (d.exp < dp) {
    return { ...d, digits: d.digits * 10n ** BigInt(dp - d.exp), exp: dp };
  }

  const divisor = 10n ** BigInt(d.exp - dp);
  const quotient = d.digits / divisor;
  const remainder = d.digits % divisor;
  // Half-up on the magnitude, which is what accounting rounding means: -2.5
  // rounds to -3, not to -2.
  const rounded = remainder * 2n >= divisor ? quotient + 1n : quotient;
  return { ...d, digits: rounded, exp: dp };
}

/**
 * The power of ten a scale string represents: "1000000" -> 6.
 *
 * Returns 0 for anything that is not a clean power of ten, which leaves the
 * value rendered at full precision rather than silently mis-scaled.
 */
export function scaleExponent(scale: string): number {
  const match = /^1(0*)$/.exec(scale.trim());
  return match ? match[1]!.length : 0;
}

function groupThousands(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function split(d: Dec): { whole: string; frac: string } {
  const raw = d.digits.toString().padStart(d.exp + 1, "0");
  return {
    whole: d.exp === 0 ? raw : raw.slice(0, raw.length - d.exp),
    frac: d.exp === 0 ? "" : raw.slice(raw.length - d.exp),
  };
}

export type NumberFormat = {
  /** Decimal places to show. Omit to keep every digit the value carries. */
  dp?: number;
  /** Render negatives as (1,234) rather than -1,234, as statements do. */
  parens?: boolean;
};

export function formatDec(value: Dec, opts: NumberFormat = {}): string {
  const d = opts.dp === undefined ? trim(value) : round(value, opts.dp);
  const { whole, frac } = split(d);

  let text = groupThousands(whole);
  if (frac) text += `.${frac}`;

  if (!isNegative(d)) return text;
  return opts.parens ? `(${text})` : `-${text}`;
}

/**
 * Format an API decimal string at a given scale.
 *
 * `scaleExp` restates the value in the units the filing printed, so a balance
 * sheet headed "$ in Millions" shows 147,957 rather than 147,957,000,000.
 */
export function formatValue(value: string, scaleExp: number, opts: NumberFormat = {}): string {
  const parsed = parseDec(value);
  if (parsed === null) return value;
  return formatDec(shift(parsed, scaleExp), opts);
}

const MAGNITUDES: ReadonlyArray<readonly [number, string]> = [
  [12, "T"],
  [9, "B"],
  [6, "M"],
  [3, "K"],
];

/** Compact form for summary tiles: 391035000000 -> "391.0B". */
export function abbreviate(value: string): string {
  const parsed = parseDec(value);
  if (parsed === null) return value;
  if (isZero(parsed)) return "0";

  const magnitude = split(parsed).whole.replace(/^0+/, "").length;
  const [places, suffix] = MAGNITUDES.find(([p]) => magnitude > p) ?? ([0, ""] as const);

  const sign = isNegative(parsed) ? "-" : "";
  const scaled = formatDec(shift({ ...parsed, neg: false }, places), {
    dp: places === 0 ? 0 : 1,
  });
  return `${sign}${scaled}${suffix}`;
}
