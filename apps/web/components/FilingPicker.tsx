"use client";

import { useEffect, useRef, useState } from "react";

import { useBoardActions } from "./BoardActions";
import { api, ApiError } from "@/lib/api";
import { filingFiledLabel, filingPeriodLabel, FORMS, type FilingForm } from "@/lib/filings";
import type { FilingIndex, Registrant } from "@/lib/types";

/** Enough history to reach a company's last few years without a long fetch. */
const LIMIT = 20;

/**
 * Browse a filer's reports and put any of them on the board.
 *
 * 10-K and 10-Q are separate lists rather than one merged timeline because
 * they are different documents, not points on a single series: one is audited
 * and annual with full statements, the other unaudited and condensed, and a
 * 10-Q balance sheet compares against fiscal year end rather than the previous
 * quarter. Interleaving them invites reading across that seam.
 */
export function FilingPicker({ registrant }: { registrant: Registrant }) {
  const { toggleFiling, prefetchFiling, openAccessions, pendingAccessions } = useBoardActions();
  const [form, setForm] = useState<FilingForm>("10-K");
  const [filings, setFilings] = useState<FilingIndex[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The registrant object is rebuilt each time ingestion reports progress, so
  // depending on it would refetch the list two or three times per search for
  // an answer that only ever depends on the CIK. The ref keeps the current
  // object reachable without making its identity a trigger.
  const current = useRef(registrant);
  current.current = registrant;

  const { cik } = registrant;

  useEffect(() => {
    const controller = new AbortController();
    setFilings(null);
    setError(null);

    api
      .filings(cik, form, LIMIT, controller.signal)
      .then((rows) => {
        setFilings(rows);
        // The newest filing is what most readers open, and the list arriving
        // is the earliest moment we know which one that is.
        const newest = rows[0];
        if (newest !== undefined) prefetchFiling(current.current, newest);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof ApiError ? cause.message : "Could not list filings.");
      });

    return () => controller.abort();
  }, [cik, form, prefetchFiling]);

  return (
    <div className="mt-4 border-t border-hairline pt-3">
      <div className="mb-2 flex items-center gap-1">
        {FORMS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setForm(option)}
            className={`nodrag eyebrow rounded px-2 py-1 text-[9px] transition ${
              option === form
                ? "bg-white/[0.08] text-ink"
                : "text-ink-faint hover:bg-white/[0.04] hover:text-ink-muted"
            }`}
          >
            {option}
          </button>
        ))}
        <span className="eyebrow ml-auto text-[8.5px] text-ink-faint">
          {filings === null && error === null ? "loading" : `${filings?.length ?? 0} filings`}
        </span>
      </div>

      {error !== null && <p className="py-2 text-[11px] text-negative">{error}</p>}

      {error === null && filings !== null && filings.length === 0 && (
        <p className="py-2 text-[11px] text-ink-faint">This filer has no {form} on EDGAR.</p>
      )}

      <div className="nowheel nodrag max-h-[260px] overflow-auto">
        {filings?.map((filing) => {
          const open = openAccessions.has(filing.accession);
          const pending = pendingAccessions.has(filing.accession);
          return (
            <button
              key={filing.accession}
              type="button"
              onClick={() => toggleFiling(registrant, filing)}
              // The pause between reading a row and clicking it is enough to
              // have fetched it. Focus counts too, so keyboard users get the
              // same head start.
              onPointerEnter={() => prefetchFiling(registrant, filing)}
              onFocus={() => prefetchFiling(registrant, filing)}
              title={
                open
                  ? "Take these statements off the board"
                  : `Open ${filing.statements.length} statements`
              }
              className={`group flex w-full items-center gap-2 rounded px-2 py-[7px] text-left transition ${
                open ? "bg-white/[0.06]" : "hover:bg-white/[0.035]"
              }`}
            >
              {/* A filled bar marks what is already on the board. Nothing is
                  drawn for a closed filing, so the list reads as text until
                  something is open. */}
              <span
                aria-hidden
                className={`h-7 w-[2px] shrink-0 rounded-full ${
                  open ? "bg-ink" : pending ? "animate-pulse bg-ink-faint" : "bg-transparent"
                }`}
              />
              <span className="min-w-0 flex-1">
                <span
                  className={`block truncate text-[11.5px] ${open ? "text-ink" : "text-ink-muted"}`}
                >
                  {filingPeriodLabel(filing)}
                </span>
                <span className="tnum block truncate text-[10px] text-ink-faint">
                  {filingFiledLabel(filing)}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
