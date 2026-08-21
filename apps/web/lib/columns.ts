import type { AsFiledColumn } from "./types";

export type ColumnGroup = {
  /** The spanning heading, e.g. "3 Months Ended". Null for instants. */
  duration: string | null;
  /** How many period columns sit under it. */
  span: number;
};

/**
 * The runs of columns sharing a duration, in order.
 *
 * A 10-Q lays its statement of operations out as two blocks side by side --
 * three months, then nine months -- and prints the same two period end dates
 * under each. Without the spanning heading above them the four columns read as
 * two pairs of duplicates, which is exactly how they looked before the parser
 * carried duration through.
 *
 * Consecutive runs rather than a grouping by value, because the order the filer
 * chose is part of the statement: rearranging columns to gather like durations
 * together would no longer be the statement as filed.
 */
export function columnGroups(columns: readonly AsFiledColumn[]): ColumnGroup[] {
  const groups: ColumnGroup[] = [];
  for (const column of columns) {
    const last = groups[groups.length - 1];
    if (last !== undefined && last.duration === column.duration) {
      last.span += 1;
    } else {
      groups.push({ duration: column.duration, span: 1 });
    }
  }
  return groups;
}

/**
 * Whether the group row is worth its vertical space.
 *
 * One group covering every column says only what the statement's own title
 * already says ("12 Months Ended" over an annual statement), so it is a row of
 * chrome. Two or more is the case it exists for, where the heading is the only
 * thing separating a quarter from its year to date.
 */
export function needsGroupRow(columns: readonly AsFiledColumn[]): boolean {
  return columnGroups(columns).filter((group) => group.duration !== null).length > 1;
}
