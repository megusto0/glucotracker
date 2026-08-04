/**
 * A small disk cache for query results that are expensive to rebuild.
 *
 * React Query's own cache lives in memory, so every reload of the app throws
 * away work the backend spent seconds producing and the page comes back with a
 * spinner. Results stored here survive a reload: the query starts with the
 * stored value already in hand and revalidates in the background, so a day
 * that has been looked at once opens instantly from then on.
 *
 * Only whole successful responses are stored, keyed by the query key. Nothing
 * here is authoritative — a miss, a parse failure or a full disk is always
 * just a normal fetch.
 */

const PREFIX = "gt:qcache:v1:";
/** Entries older than this are dropped rather than shown. */
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;
/** Keeps one oversized response from filling the whole quota. */
const MAX_ENTRY_BYTES = 512 * 1024;
const MAX_ENTRIES = 120;

type StoredEntry<T> = {
  data: T;
  updatedAt: number;
};

export type PersistedEntry<T> = {
  data: T;
  updatedAt: number;
};

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function storageKey(queryKey: readonly unknown[]) {
  return `${PREFIX}${JSON.stringify(queryKey)}`;
}

export function readPersistedQuery<T>(
  queryKey: readonly unknown[],
): PersistedEntry<T> | undefined {
  const store = storage();
  if (!store) return undefined;
  try {
    const raw = store.getItem(storageKey(queryKey));
    if (!raw) return undefined;
    const entry = JSON.parse(raw) as StoredEntry<T>;
    if (
      typeof entry?.updatedAt !== "number" ||
      entry.data === undefined ||
      Date.now() - entry.updatedAt > MAX_AGE_MS
    ) {
      store.removeItem(storageKey(queryKey));
      return undefined;
    }
    return { data: entry.data, updatedAt: entry.updatedAt };
  } catch {
    return undefined;
  }
}

export function writePersistedQuery<T>(
  queryKey: readonly unknown[],
  data: T,
): void {
  const store = storage();
  if (!store) return;
  try {
    const serialized = JSON.stringify({
      data,
      updatedAt: Date.now(),
    } satisfies StoredEntry<T>);
    if (serialized.length > MAX_ENTRY_BYTES) return;
    store.setItem(storageKey(queryKey), serialized);
    pruneOldest(store);
  } catch {
    // A full or unavailable quota is not worth reporting: the next request
    // simply goes to the network. Clear our own entries and move on.
    evictAll();
  }
}

/** Drop the least recently written entries once the cache gets crowded. */
function pruneOldest(store: Storage): void {
  const entries: { key: string; updatedAt: number }[] = [];
  for (let index = 0; index < store.length; index += 1) {
    const key = store.key(index);
    if (!key?.startsWith(PREFIX)) continue;
    try {
      const parsed = JSON.parse(store.getItem(key) ?? "{}") as StoredEntry<
        unknown
      >;
      entries.push({ key, updatedAt: parsed?.updatedAt ?? 0 });
    } catch {
      entries.push({ key, updatedAt: 0 });
    }
  }
  if (entries.length <= MAX_ENTRIES) return;
  entries
    .sort((left, right) => left.updatedAt - right.updatedAt)
    .slice(0, entries.length - MAX_ENTRIES)
    .forEach((entry) => store.removeItem(entry.key));
}

export function evictAll(): void {
  const store = storage();
  if (!store) return;
  try {
    const keys: string[] = [];
    for (let index = 0; index < store.length; index += 1) {
      const key = store.key(index);
      if (key?.startsWith(PREFIX)) keys.push(key);
    }
    keys.forEach((key) => store.removeItem(key));
  } catch {
    // Nothing to do: the cache is advisory.
  }
}
