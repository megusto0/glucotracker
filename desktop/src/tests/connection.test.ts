import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { http, HttpResponse } from "msw";
import { server } from "./msw";
import { useSettingsStore } from "../features/settings/settingsStore";
import { ConnectionBanner } from "../components/ConnectionBanner";
import { connectionManager } from "../api/connectionManager";
import { apiClient } from "../api/client";

describe("connectionManager", () => {
  beforeEach(() => {
    useSettingsStore.setState({
      baseUrl: "http://api.test",
      token: "test-token",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("scenario: normal startup transitions to connected", async () => {
    server.use(
      http.get("http://api.test/health", () =>
        HttpResponse.json({ status: "ok", version: "0.1.0", db: "ok" }),
      ),
    );

    const statuses: string[] = [];
    const unsubscribe = connectionManager.subscribe((s) => statuses.push(s));

    connectionManager.init(() => useSettingsStore.getState());

    await waitFor(
      () => expect(statuses).toContain("connected"),
      { timeout: 10_000 },
    );

    expect(connectionManager.getStatus()).toBe("connected");
    unsubscribe();
    connectionManager.destroy();
  }, 15_000);

  it("scenario: backend unreachable triggers disconnected with backoff", async () => {
    server.use(
      http.get("http://api.test/health", () =>
        new HttpResponse(null, { status: 503, statusText: "Service Unavailable" }),
      ),
    );

    const statuses: string[] = [];
    const unsubscribe = connectionManager.subscribe((s) => statuses.push(s));

    connectionManager.init(() => useSettingsStore.getState());

    await waitFor(
      () => expect(statuses).toContain("disconnected"),
      { timeout: 10_000 },
    );

    expect(connectionManager.getStatus()).toBe("disconnected");
    const state = connectionManager.getState();
    expect(state.consecutiveFailures).toBeGreaterThan(0);
    expect(state.lastError).toBeTruthy();
    unsubscribe();
    connectionManager.destroy();
  }, 15_000);

  it("scenario: recovery after backend comes back online", async () => {
    let callCount = 0;

    server.use(
      http.get("http://api.test/health", () => {
        callCount++;
        if (callCount <= 2) {
          return new HttpResponse(null, { status: 503 });
        }
        return HttpResponse.json({ status: "ok", version: "0.1.0", db: "ok" });
      }),
    );

    const statuses: string[] = [];
    const unsubscribe = connectionManager.subscribe((s) => statuses.push(s));

    connectionManager.init(() => useSettingsStore.getState());

    await waitFor(
      () => expect(statuses).toContain("disconnected"),
      { timeout: 10_000 },
    );

    await waitFor(
      () => expect(statuses).toContain("connected"),
      { timeout: 60_000 },
    );

    unsubscribe();
    connectionManager.destroy();
  }, 65_000);

  it("scenario: notifyRequestSucceeded recovers from degraded", async () => {
    connectionManager.init(() => useSettingsStore.getState());

    (connectionManager as unknown as { state: { status: string; consecutiveFailures: number } }).state.status = "degraded";
    (connectionManager as unknown as { state: { status: string; consecutiveFailures: number } }).state.consecutiveFailures = 2;

    connectionManager.notifyRequestSucceeded();

    expect(connectionManager.getStatus()).toBe("connected");
    expect(connectionManager.getState().consecutiveFailures).toBe(0);

    connectionManager.destroy();
  });

  it("scenario: notifyRequestFailed transitions to disconnected after sustained failures", async () => {
    connectionManager.init(() => useSettingsStore.getState());

    (connectionManager as unknown as { state: { status: string } }).state.status = "connected";

    connectionManager.notifyRequestFailed("err1");
    expect(connectionManager.getStatus()).toBe("connected");

    connectionManager.notifyRequestFailed("err2");
    expect(connectionManager.getStatus()).toBe("connected");

    connectionManager.notifyRequestFailed("err3");
    expect(connectionManager.getStatus()).toBe("degraded");

    connectionManager.notifyRequestFailed("err4");
    connectionManager.notifyRequestFailed("err5");
    connectionManager.notifyRequestFailed("err6");
    expect(connectionManager.getStatus()).toBe("disconnected");

    connectionManager.destroy();
  });

  it("scenario: circuit breaker opens after 10 failures", async () => {
    connectionManager.init(() => useSettingsStore.getState());

    const internal = connectionManager as unknown as {
      state: { status: string; circuitOpen: boolean; consecutiveFailures: number; autoRecoveryAttempt: number };
    };
    internal.state.status = "disconnected";
    internal.state.consecutiveFailures = 9;

    connectionManager.notifyRequestFailed("err10");

    expect(connectionManager.getState().circuitOpen).toBe(true);

    const log = connectionManager.getLogEntries();
    expect(log.some((e) => e.type === "circuit_open")).toBe(true);

    connectionManager.destroy();
  });

  it("scenario: circuit breaker closes on request success", async () => {
    connectionManager.init(() => useSettingsStore.getState());

    const internal = connectionManager as unknown as {
      state: { status: string; circuitOpen: boolean; consecutiveFailures: number };
    };
    internal.state.status = "disconnected";
    internal.state.circuitOpen = true;
    internal.state.consecutiveFailures = 5;

    connectionManager.notifyRequestSucceeded();

    expect(connectionManager.getState().circuitOpen).toBe(false);
    expect(connectionManager.getStatus()).toBe("connected");

    connectionManager.destroy();
  });

  it("scenario: connection manager logs are exportable", async () => {
    server.use(
      http.get("http://api.test/health", () =>
        HttpResponse.json({ status: "ok", version: "0.1.0", db: "ok" }),
      ),
    );

    connectionManager.init(() => useSettingsStore.getState());

    await waitFor(
      () => expect(connectionManager.getStatus()).toBe("connected"),
      { timeout: 10_000 },
    );

    const log = connectionManager.exportLog();
    expect(log.length).toBeGreaterThan(0);
    expect(log).toContain("HEALTH_CHECK");

    connectionManager.destroy();
  }, 15_000);

  it("scenario: routine health check does not enter checking state while connected", async () => {
    server.use(
      http.get("http://api.test/health", () =>
        HttpResponse.json({ status: "ok", version: "0.1.0", db: "ok" }),
      ),
    );

    const statuses: string[] = [];
    const unsubscribe = connectionManager.subscribe((s) => statuses.push(s));
    connectionManager.init(() => useSettingsStore.getState());
    (connectionManager as unknown as { state: { status: string } }).state.status = "connected";

    await connectionManager.forceCheck();

    expect(connectionManager.getStatus()).toBe("connected");
    expect(statuses).not.toContain("checking");

    unsubscribe();
    connectionManager.destroy();
  });

  it("scenario: DB unavailable triggers degraded status", async () => {
    server.use(
      http.get("http://api.test/health", () =>
        HttpResponse.json({ status: "ok", version: "0.1.0", db: "unavailable" }),
      ),
    );

    connectionManager.init(() => useSettingsStore.getState());

    await waitFor(
      () => expect(connectionManager.getStatus()).toBe("degraded"),
      { timeout: 10_000 },
    );

    expect(connectionManager.getState().lastError).toBe("database unavailable");

    connectionManager.destroy();
  }, 15_000);
});

describe("ConnectionBanner", () => {
  it("renders nothing when connected", async () => {
    useSettingsStore.setState({
      baseUrl: "http://api.test",
      token: "test-token",
    });
    connectionManager.init(() => useSettingsStore.getState());
    (connectionManager as unknown as { state: { status: string } }).state.status = "connected";

    const { container } = render(createElement(ConnectionBanner));
    expect(container.firstChild).toBeNull();

    connectionManager.destroy();
  });

  it("renders warning when disconnected", async () => {
    useSettingsStore.setState({
      baseUrl: "http://api.test",
      token: "test-token",
    });
    connectionManager.destroy();
    const manager = connectionManager as unknown as {
      state: { consecutiveFailures: number; lastError: string; status: string };
    };
    manager.state.status = "disconnected";
    manager.state.consecutiveFailures = 1;
    manager.state.lastError = "offline";

    render(createElement(ConnectionBanner));

    await waitFor(
      () => {
        expect(screen.getByText(/Backend недоступен/)).toBeTruthy();
      },
      { timeout: 7_000 },
    );

    connectionManager.destroy();
  }, 10_000);
});

describe("API client default timeout", () => {
  beforeEach(() => {
    useSettingsStore.setState({
      baseUrl: "http://api.test",
      token: "test-token",
    });
  });

  it("should timeout after 30 seconds by default", async () => {
    vi.useFakeTimers();

    server.use(
      http.get("http://api.test/health", async () => {
        await new Promise(() => {});
      }),
    );

    const promise = apiClient.health(useSettingsStore.getState());

    vi.advanceTimersByTime(30_000);

    try {
      await promise;
      expect.unreachable("Should have timed out");
    } catch (e: unknown) {
      expect((e as Error).message).toContain("30");
    }

    vi.useRealTimers();
  }, 10_000);
});
