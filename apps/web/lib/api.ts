import type {
  AsFiledStatement,
  Entity,
  FilingIndex,
  Registrant,
  Validation,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Params = Record<string, string | number | boolean | undefined>;

async function request<T>(
  path: string,
  { method = "GET", params, signal }: { method?: string; params?: Params; signal?: AbortSignal } = {},
): Promise<T> {
  const url = new URL(path, BASE);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }

  let response: Response;
  try {
    response = await fetch(url, { method, signal });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    // A dead API is the most likely failure in development, and "Failed to
    // fetch" gives the user nothing to act on.
    throw new ApiError(0, `Cannot reach the API at ${BASE}. Is it running?`);
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => undefined);
    throw new ApiError(response.status, detail ?? `${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

export const api = {
  search: async (q: string, signal?: AbortSignal) => {
    // Over-fetch, then collapse to one row per filer. A large issuer carries a
    // ticker per preferred class and structured note -- "JPMORGAN" returns JPM,
    // JPM-PC, JPM-PD, JPM-PJ, VYLD and more, every one of them CIK 19617. Asked
    // for eight rows, EDGAR fills all eight with the same company and crowds out
    // every other match.
    const { results } = await request<{ results: Registrant[] }>("/entities/search", {
      params: { q, limit: 40 },
      signal,
    });

    const byFiler = new Map<number, Registrant>();
    for (const registrant of results) {
      // First wins: EDGAR lists the common stock ahead of its derivatives.
      if (!byFiler.has(registrant.cik)) byFiler.set(registrant.cik, registrant);
    }
    return { results: [...byFiler.values()].slice(0, 8) };
  },

  /** Begin ingestion. Returns immediately with `state: "ingesting"`. */
  resolveCik: (cik: number, ticker: string) =>
    request<Entity>("/entities/resolve-cik", { method: "POST", params: { cik, ticker } }),

  entity: (cik: number, signal?: AbortSignal) =>
    request<Entity>(`/entities/${cik}`, { signal }),

  filings: (cik: number, form = "10-K", limit = 8, signal?: AbortSignal) =>
    request<FilingIndex[]>(`/entities/${cik}/filings`, { params: { form, limit }, signal }),

  asFiled: (cik: number, form = "10-K", accession?: string, signal?: AbortSignal) =>
    request<AsFiledStatement[]>(`/entities/${cik}/as-filed`, {
      params: { form, accession },
      signal,
    }),

  validation: (cik: number, status?: string, signal?: AbortSignal) =>
    request<Validation>(`/entities/${cik}/validation`, { params: { status }, signal }),
};

/**
 * Poll until ingestion settles.
 *
 * The API returns 409 while ingesting rather than holding a request open, so
 * the wait belongs on the client. The as-filed statements do not depend on this
 * finishing -- they render first, and the ledger fills in behind them.
 */
export async function waitForEntity(
  cik: number,
  onProgress: (entity: Entity) => void,
  signal?: AbortSignal,
): Promise<Entity> {
  const INTERVAL_MS = 1200;

  for (;;) {
    const entity = await api.entity(cik, signal);
    onProgress(entity);
    if (entity.state !== "ingesting") return entity;

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, INTERVAL_MS);
      signal?.addEventListener(
        "abort",
        () => {
          clearTimeout(timer);
          reject(signal.reason);
        },
        { once: true },
      );
    });
  }
}
