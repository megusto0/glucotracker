import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { server } from "../../../tests/msw";
import { useSettingsStore } from "../../settings/settingsStore";
import { glucoseSyncLogger } from "../glucoseSyncLogger";

const IMPORT_URL = "http://api.test/nightscout/import";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: 0, staleTime: 0 } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useGlucoseSyncTracker integration", () => {
  beforeEach(() => {
    glucoseSyncLogger.clear();
    useSettingsStore.setState({
      baseUrl: "http://api.test",
      token: "test-token",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("scenario: disabled when Nightscout not configured", async () => {
    const { useGlucoseSyncTracker } = await import("../useGlucoseSyncTracker");

    const { result } = renderHook(
      () =>
        useGlucoseSyncTracker(
          "2026-04-28T04:00:00",
          "2026-04-28T10:00:00",
          "normalized",
          false,
          false,
        ),
      { wrapper: createWrapper() },
    );

    expect(result.current.syncState.phase).toBe("idle");
  });

  it("scenario: network error triggers backoff and logging", async () => {
    let importCallCount = 0;

    server.use(
      http.post(IMPORT_URL, () => {
        importCallCount++;
        return new HttpResponse(null, { status: 503, statusText: "Service Unavailable" });
      }),
    );

    const { useGlucoseSyncTracker } = await import("../useGlucoseSyncTracker");

    const { result } = renderHook(
      () =>
        useGlucoseSyncTracker(
          "2026-04-28T04:00:00",
          "2026-04-28T10:00:00",
          "normalized",
          true,
          true,
        ),
      { wrapper: createWrapper() },
    );

    await waitFor(
      () => {
        expect(importCallCount).toBeGreaterThanOrEqual(1);
      },
      { timeout: 15000 },
    );

    await waitFor(
      () => {
        expect(result.current.syncState.consecutiveErrors).toBeGreaterThan(0);
      },
      { timeout: 10000 },
    );

    expect(result.current.syncState.lastError).toBeTruthy();
    expect(glucoseSyncLogger.getEntries("error").length).toBeGreaterThan(0);
  }, 30000);

  it("scenario: forceRefresh triggers immediate import", async () => {
    let importCalled = false;

    server.use(
      http.post(IMPORT_URL, () => {
        importCalled = true;
        return HttpResponse.json({
          from_datetime: "2026-04-28T04:00:00",
          to_datetime: "2026-04-28T10:00:00",
          glucose_imported: 0,
          insulin_imported: 0,
          glucose_total: 0,
          insulin_total: 0,
        });
      }),
    );

    const { useGlucoseSyncTracker } = await import("../useGlucoseSyncTracker");

    const { result } = renderHook(
      () =>
        useGlucoseSyncTracker(
          "2026-04-28T04:00:00",
          "2026-04-28T10:00:00",
          "normalized",
          true,
          true,
        ),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      result.current.forceRefresh();
    });

    await waitFor(
      () => {
        expect(importCalled).toBe(true);
      },
      { timeout: 15000 },
    );
  }, 30000);

  it("scenario: normal update with new data", async () => {
    let importCallCount = 0;

    server.use(
      http.post(IMPORT_URL, () => {
        importCallCount++;
        return HttpResponse.json({
          from_datetime: "2026-04-28T04:00:00",
          to_datetime: "2026-04-28T10:00:00",
          glucose_imported: 2,
          insulin_imported: 0,
          glucose_total: 2,
          insulin_total: 0,
        });
      }),
    );

    const { useGlucoseSyncTracker } = await import("../useGlucoseSyncTracker");

    const { result } = renderHook(
      () =>
        useGlucoseSyncTracker(
          "2026-04-28T04:00:00",
          "2026-04-28T10:00:00",
          "normalized",
          true,
          true,
        ),
      { wrapper: createWrapper() },
    );

    await waitFor(
      () => {
        expect(importCallCount).toBeGreaterThanOrEqual(1);
      },
      { timeout: 15000 },
    );

    const summary = result.current.logSummary();
    expect(summary.total).toBeGreaterThan(0);
    expect(glucoseSyncLogger.getEntries("info").length).toBeGreaterThan(0);
  }, 30000);

  it("scenario: resetConnection clears offline state", async () => {
    const { useGlucoseSyncTracker } = await import("../useGlucoseSyncTracker");

    const { result } = renderHook(
      () =>
        useGlucoseSyncTracker(
          "2026-04-28T04:00:00",
          "2026-04-28T10:00:00",
          "normalized",
          true,
          true,
        ),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      result.current.resetConnection();
    });

    expect(result.current.syncState.consecutiveErrors).toBe(0);
    expect(result.current.syncState.lastError).toBeNull();
  });
});
