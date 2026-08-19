"use client";

import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Registrant } from "@/lib/types";

export function TickerSearch({
  onPick,
  busy,
}: {
  onPick: (registrant: Registrant) => void;
  busy: boolean;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Registrant[]>([]);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "/" && document.activeElement !== inputRef.current) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setError(null);
      return;
    }

    // Debounced and aborted on every keystroke: the SEC asks for no more than
    // ten requests a second, and a search-as-you-type box is the easiest way to
    // breach that by accident.
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api
        .search(trimmed, controller.signal)
        .then((response) => {
          setResults(response.results);
          setActive(0);
          setError(null);
        })
        .catch((cause: unknown) => {
          if (controller.signal.aborted) return;
          setError(cause instanceof ApiError ? cause.message : "Search failed.");
        });
    }, 180);

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query]);

  const choose = (registrant: Registrant) => {
    setQuery("");
    setResults([]);
    inputRef.current?.blur();
    onPick(registrant);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      const picked = results[active];
      if (picked) choose(picked);
    } else if (event.key === "Escape") {
      setQuery("");
      setResults([]);
    }
  };

  return (
    <div className="relative w-[420px]">
      <div className="panel flex items-center gap-3 rounded-lg px-4 py-2.5">
        <svg
          viewBox="0 0 20 20"
          className="h-4 w-4 shrink-0 fill-none stroke-ink-faint stroke-[1.6]"
        >
          <circle cx="9" cy="9" r="6" />
          <path d="m13.5 13.5 3.5 3.5" strokeLinecap="round" />
        </svg>
        <input
          ref={inputRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search a ticker or company…"
          spellCheck={false}
          className="w-full bg-transparent text-[13px] text-ink outline-none placeholder:text-ink-faint"
        />
        {busy ? (
          <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-[1.5px] border-hairline-strong border-t-ink" />
        ) : (
          <kbd className="shrink-0 rounded border border-hairline-strong px-1.5 py-0.5 text-[10px] text-ink-faint">
            /
          </kbd>
        )}
      </div>

      {(results.length > 0 || error) && (
        <div className="panel absolute left-0 right-0 top-full z-20 mt-2 overflow-hidden rounded-lg">
          {error && <div className="px-4 py-3 text-[12px] text-negative">{error}</div>}
          {results.map((registrant, index) => (
            <button
              key={registrant.cik}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(registrant)}
              className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition ${
                index === active ? "bg-raised" : "hover:bg-raised/60"
              }`}
            >
              <span className="tabular w-14 shrink-0 text-[12px] font-semibold text-ink">
                {registrant.ticker}
              </span>
              <span className="truncate text-[12px] text-ink-muted">{registrant.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
