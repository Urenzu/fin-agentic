/**
 * Fetching a filing before the reader asks for it.
 *
 * Opening a filing costs a round trip to our API and, on a cold cache, several
 * more from there to EDGAR. The reader spends a moment reading the filing list
 * before clicking, and that moment is long enough to have done the work.
 *
 * Two things make this safe to do speculatively. The request is a plain GET of
 * public filing data, so issuing one that is never used costs a little
 * bandwidth and nothing else. And a filing is immutable once submitted, so a
 * response can be held indefinitely without going stale.
 */

export type Loader<T> = (signal?: AbortSignal) => Promise<T>;

/**
 * A keyed store of in-flight and settled requests.
 *
 * Holds the *promise* rather than the value, which is what makes a hover
 * followed immediately by a click cheap: the click joins the request the hover
 * started instead of racing a second one alongside it.
 *
 * A rejected entry is dropped so the next attempt is a real retry. Keeping it
 * would mean one failure -- a dropped connection while the pointer happened to
 * pass over a row -- permanently poisoning that filing.
 */
export class RequestCache<T> {
  private readonly entries = new Map<string, Promise<T>>();

  constructor(private readonly limit = 40) {}

  get size(): number {
    return this.entries.size;
  }

  has(key: string): boolean {
    return this.entries.has(key);
  }

  /** Run `load` unless this key is already in flight or settled. */
  fetch(key: string, load: Loader<T>): Promise<T> {
    const existing = this.entries.get(key);
    if (existing !== undefined) {
      // Refresh recency so a filing being read is not the one evicted.
      this.entries.delete(key);
      this.entries.set(key, existing);
      return existing;
    }

    const pending = load().catch((cause: unknown) => {
      this.entries.delete(key);
      throw cause;
    });

    this.entries.set(key, pending);
    this.evict();
    return pending;
  }

  /**
   * Start a request and ignore the outcome.
   *
   * Speculative work must never surface an error: the reader did not ask for
   * this and has nothing to do about it. A real failure is reported when they
   * click, because `fetch` drops the rejected entry and the click retries.
   */
  warm(key: string, load: Loader<T>): void {
    if (this.entries.has(key)) return;
    void this.fetch(key, load).catch(() => undefined);
  }

  private evict(): void {
    while (this.entries.size > this.limit) {
      const oldest = this.entries.keys().next();
      if (oldest.done === true) return;
      this.entries.delete(oldest.value);
    }
  }
}

export function filingKey(cik: number, form: string, accession: string): string {
  return `${cik}:${form}:${accession}`;
}
