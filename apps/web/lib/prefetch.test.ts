import assert from "node:assert/strict";
import { test } from "node:test";

import { filingKey, RequestCache } from "./prefetch";

/** A loader that resolves when the test says so, counting its calls. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (cause: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

test("a second request for the same key joins the first", async () => {
  const cache = new RequestCache<string>();
  let calls = 0;
  const gate = deferred<string>();
  const load = () => {
    calls += 1;
    return gate.promise;
  };

  const first = cache.fetch("k", load);
  const second = cache.fetch("k", load);
  gate.resolve("payload");

  assert.equal(await first, "payload");
  assert.equal(await second, "payload");
  assert.equal(calls, 1);
});

test("a click lands on the request the hover already started", async () => {
  // The point of holding the promise rather than the value.
  const cache = new RequestCache<string>();
  let calls = 0;
  const gate = deferred<string>();

  cache.warm("k", () => {
    calls += 1;
    return gate.promise;
  });
  const clicked = cache.fetch("k", () => {
    calls += 1;
    return Promise.resolve("second");
  });

  gate.resolve("first");
  assert.equal(await clicked, "first");
  assert.equal(calls, 1);
});

test("a settled response is reused without refetching", async () => {
  const cache = new RequestCache<string>();
  let calls = 0;
  const load = () => {
    calls += 1;
    return Promise.resolve("payload");
  };

  await cache.fetch("k", load);
  assert.equal(await cache.fetch("k", load), "payload");
  assert.equal(calls, 1);
});

test("a failure is dropped so the next attempt is a real retry", async () => {
  // Otherwise one dropped connection while the pointer passed over a row would
  // poison that filing for the rest of the session.
  const cache = new RequestCache<string>();
  let calls = 0;
  const load = () => {
    calls += 1;
    return calls === 1 ? Promise.reject(new Error("network")) : Promise.resolve("payload");
  };

  await assert.rejects(() => cache.fetch("k", load), /network/);
  assert.equal(cache.has("k"), false);
  assert.equal(await cache.fetch("k", load), "payload");
  assert.equal(calls, 2);
});

test("speculative warming never raises", async () => {
  const cache = new RequestCache<string>();
  cache.warm("k", () => Promise.reject(new Error("network")));
  // Let the rejection settle; an unhandled one would fail the test run.
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(cache.has("k"), false);
});

test("warming an entry already present starts nothing", async () => {
  const cache = new RequestCache<string>();
  let calls = 0;
  await cache.fetch("k", () => {
    calls += 1;
    return Promise.resolve("payload");
  });

  cache.warm("k", () => {
    calls += 1;
    return Promise.resolve("again");
  });
  assert.equal(calls, 1);
});

test("the cache is bounded, evicting the least recently used", async () => {
  const cache = new RequestCache<string>(2);
  await cache.fetch("a", () => Promise.resolve("a"));
  await cache.fetch("b", () => Promise.resolve("b"));
  await cache.fetch("a", () => Promise.resolve("stale")); // "b" is now oldest
  await cache.fetch("c", () => Promise.resolve("c"));

  assert.equal(cache.size, 2);
  assert.equal(cache.has("a"), true);
  assert.equal(cache.has("b"), false);
  assert.equal(cache.has("c"), true);
});

test("keys separate filings, forms and filers", () => {
  const accession = "0000320193-25-000079";
  assert.notEqual(filingKey(320193, "10-K", accession), filingKey(320193, "10-Q", accession));
  assert.notEqual(filingKey(320193, "10-K", accession), filingKey(789019, "10-K", accession));
  assert.equal(filingKey(320193, "10-K", accession), filingKey(320193, "10-K", accession));
});
