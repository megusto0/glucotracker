import { afterEach, describe, expect, test, vi } from "vitest";
import {
  evictAll,
  readPersistedQuery,
  writePersistedQuery,
} from "../api/persistentQueryCache";

const key = ["glucose", "therapy-review", "2026-07-25", 6, 120] as const;

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("persistentQueryCache", () => {
  test("a stored result survives to the next session", () => {
    writePersistedQuery(key, { items: [{ title: "Обед" }] });

    const entry = readPersistedQuery<{ items: { title: string }[] }>(key);
    expect(entry?.data.items[0]?.title).toBe("Обед");
    expect(entry?.updatedAt).toBeGreaterThan(0);
  });

  test("different query keys never read each other's entry", () => {
    writePersistedQuery(key, "day");

    expect(
      readPersistedQuery(["glucose", "therapy-review", "2026-07-26", 6, 120]),
    ).toBeUndefined();
  });

  test("an entry past its lifetime is dropped rather than shown", () => {
    writePersistedQuery(key, "stale");
    vi.setSystemTime(new Date(Date.now() + 31 * 24 * 60 * 60 * 1000));

    expect(readPersistedQuery(key)).toBeUndefined();
    vi.useRealTimers();
  });

  test("corrupted storage reads as a miss instead of throwing", () => {
    window.localStorage.setItem(
      `gt:qcache:v1:${JSON.stringify(key)}`,
      "{not json",
    );

    expect(() => readPersistedQuery(key)).not.toThrow();
    expect(readPersistedQuery(key)).toBeUndefined();
  });

  test("a full quota clears the cache instead of failing the query", () => {
    writePersistedQuery(key, "first");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });

    expect(() => writePersistedQuery(key, "second")).not.toThrow();
    vi.restoreAllMocks();
    expect(readPersistedQuery(key)).toBeUndefined();
  });

  test("eviction only touches this cache's own keys", () => {
    window.localStorage.setItem("unrelated", "keep me");
    writePersistedQuery(key, "day");

    evictAll();

    expect(window.localStorage.getItem("unrelated")).toBe("keep me");
    expect(readPersistedQuery(key)).toBeUndefined();
  });
});
