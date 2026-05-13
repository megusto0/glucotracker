import { apiClient } from "./client";
import type { ApiConfig } from "./client";

export type ConnectionStatus =
  | "connected"
  | "degraded"
  | "disconnected"
  | "checking";

export interface ConnectionEvent {
  timestamp: string;
  type:
    | "status_change"
    | "health_check"
    | "recovery_attempt"
    | "network_online"
    | "network_offline"
    | "request_failure"
    | "refetch_triggered"
    | "circuit_open"
    | "circuit_close"
    | "auto_recovery";
  from?: ConnectionStatus;
  to?: ConnectionStatus;
  latencyMs?: number;
  error?: string;
  details?: Record<string, unknown>;
}

interface ConnectionManagerState {
  status: ConnectionStatus;
  lastHealthCheckAt: string | null;
  lastConnectedAt: string | null;
  lastError: string | null;
  consecutiveFailures: number;
  latencyMs: number | null;
  circuitOpen: boolean;
  autoRecoveryAttempt: number;
}

type Listener = (
  status: ConnectionStatus,
  state: ConnectionManagerState,
) => void;

const HEALTH_CHECK_INTERVAL_MS = 30_000;
const DEGRADED_THRESHOLD_MS = 5_000;
const MAX_BACKOFF_MS = 5 * 60_000;
const BACKOFF_BASE_MS = 5_000;
const MAX_LOG_ENTRIES = 200;
const CIRCUIT_BREAKER_THRESHOLD = 10;
const CIRCUIT_BREAKER_RESET_MS = 60_000;
const AUTO_RECOVERY_MAX_ATTEMPTS = 3;
const REQUEST_FAILURE_DEGRADED_THRESHOLD = 3;
const REQUEST_FAILURE_DISCONNECTED_THRESHOLD = 6;

const entries: ConnectionEvent[] = [];

const initialConnectionState = (): ConnectionManagerState => ({
  status: "disconnected",
  lastHealthCheckAt: null,
  lastConnectedAt: null,
  lastError: null,
  consecutiveFailures: 0,
  latencyMs: null,
  circuitOpen: false,
  autoRecoveryAttempt: 0,
});

function pushEvent(event: Omit<ConnectionEvent, "timestamp">) {
  entries.push({ ...event, timestamp: new Date().toISOString() });
  if (entries.length > MAX_LOG_ENTRIES) {
    entries.splice(0, entries.length - MAX_LOG_ENTRIES);
  }
}

class ConnectionManager {
  private state: ConnectionManagerState = initialConnectionState();

  private listeners = new Set<Listener>();
  private healthCheckTimer: ReturnType<typeof setTimeout> | null = null;
  private configGetter: (() => ApiConfig) | null = null;
  private onlineHandler: (() => void) | null = null;
  private offlineHandler: (() => void) | null = null;
  private visibilityHandler: (() => void) | null = null;
  private circuitResetTimer: ReturnType<typeof setTimeout> | null = null;
  private initialized = false;

  init(configGetter: () => ApiConfig) {
    if (this.initialized) return;
    this.initialized = true;
    this.configGetter = configGetter;

    this.onlineHandler = () => {
      pushEvent({ type: "network_online" });
      if (this.state.status === "disconnected") {
        this.scheduleHealthCheck(1_000);
      }
    };

    this.offlineHandler = () => {
      pushEvent({ type: "network_offline" });
      this.setStatus("disconnected");
    };

    this.visibilityHandler = () => {
      if (document.visibilityState === "visible") {
        if (
          this.state.status === "disconnected" ||
          this.state.status === "degraded"
        ) {
          const lastCheck = this.state.lastHealthCheckAt;
          const stale =
            !lastCheck ||
            Date.now() - new Date(lastCheck).getTime() > HEALTH_CHECK_INTERVAL_MS;
          if (stale) {
            pushEvent({
              type: "recovery_attempt",
              details: { trigger: "visibility_change" },
            });
            this.scheduleHealthCheck(500);
          }
        }
      }
    };

    window.addEventListener("online", this.onlineHandler);
    window.addEventListener("offline", this.offlineHandler);
    document.addEventListener("visibilitychange", this.visibilityHandler);

    this.scheduleHealthCheck(2_000);
  }

  destroy() {
    if (this.healthCheckTimer !== null) {
      clearTimeout(this.healthCheckTimer);
      this.healthCheckTimer = null;
    }
    if (this.circuitResetTimer !== null) {
      clearTimeout(this.circuitResetTimer);
      this.circuitResetTimer = null;
    }
    if (this.onlineHandler) {
      window.removeEventListener("online", this.onlineHandler);
    }
    if (this.offlineHandler) {
      window.removeEventListener("offline", this.offlineHandler);
    }
    if (this.visibilityHandler) {
      document.removeEventListener("visibilitychange", this.visibilityHandler);
    }
    this.listeners.clear();
    this.state = initialConnectionState();
    this.configGetter = null;
    this.initialized = false;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  getStatus(): ConnectionStatus {
    return this.state.status;
  }

  getState(): Readonly<ConnectionManagerState> {
    return this.state;
  }

  getLatencyMs(): number | null {
    return this.state.latencyMs;
  }

  forceCheck(): Promise<ConnectionStatus> {
    return this.performHealthCheck();
  }

  notifyRequestFailed(error: string) {
    if (this.state.circuitOpen) return;

    this.state.consecutiveFailures++;
    this.state.lastError = error;
    pushEvent({
      type: "request_failure",
      error,
      details: { consecutiveFailures: this.state.consecutiveFailures },
    });

    if (
      this.state.status === "connected" ||
      this.state.status === "degraded"
    ) {
      if (
        this.state.consecutiveFailures >=
        REQUEST_FAILURE_DISCONNECTED_THRESHOLD
      ) {
        this.setStatus("disconnected");
        this.scheduleHealthCheck(
          Math.min(
            BACKOFF_BASE_MS * this.state.consecutiveFailures,
            MAX_BACKOFF_MS,
          ),
        );
      } else if (
        this.state.consecutiveFailures >= REQUEST_FAILURE_DEGRADED_THRESHOLD
      ) {
        this.setStatus("degraded");
        this.scheduleHealthCheck(3_000);
      } else {
        this.scheduleHealthCheck(1_500);
      }
    }

    if (this.state.consecutiveFailures >= CIRCUIT_BREAKER_THRESHOLD) {
      this.openCircuitBreaker();
    }
  }

  notifyRequestSucceeded() {
    this.state.consecutiveFailures = 0;
    this.state.autoRecoveryAttempt = 0;

    if (this.state.circuitOpen) {
      this.closeCircuitBreaker();
    }

    if (this.state.status !== "connected") {
      this.state.lastError = null;
      this.setStatus("connected");
      pushEvent({
        type: "recovery_attempt",
        to: "connected",
        details: { trigger: "request_success" },
      });
    }
  }

  exportLog(): string {
    return entries
      .map((e) => {
        const parts = [e.timestamp, e.type.toUpperCase()];
        if (e.from && e.to) parts.push(`${e.from}->${e.to}`);
        if (e.latencyMs !== undefined) parts.push(`${e.latencyMs}ms`);
        if (e.error) parts.push(`error=${e.error}`);
        if (e.details) parts.push(JSON.stringify(e.details));
        return parts.join(" ");
      })
      .join("\n");
  }

  getLogEntries(): readonly ConnectionEvent[] {
    return entries;
  }

  private setStatus(status: ConnectionStatus) {
    if (this.state.status === status) return;
    const prev = this.state.status;
    this.state.status = status;

    if (status === "connected") {
      this.state.lastConnectedAt = new Date().toISOString();
      this.state.consecutiveFailures = 0;
      this.state.lastError = null;
      this.state.autoRecoveryAttempt = 0;
    }

    pushEvent({ type: "status_change", from: prev, to: status });
    this.notifyListeners();
  }

  private openCircuitBreaker() {
    if (this.state.circuitOpen) return;
    this.state.circuitOpen = true;

    pushEvent({
      type: "circuit_open",
      details: {
        consecutiveFailures: this.state.consecutiveFailures,
        message: "Circuit breaker opened: too many failures",
      },
    });

    if (this.circuitResetTimer !== null) {
      clearTimeout(this.circuitResetTimer);
    }

    const attempt = this.state.autoRecoveryAttempt + 1;
    this.state.autoRecoveryAttempt = attempt;

    if (attempt <= AUTO_RECOVERY_MAX_ATTEMPTS) {
      const resetDelay =
        CIRCUIT_BREAKER_RESET_MS * Math.pow(2, attempt - 1);
      pushEvent({
        type: "auto_recovery",
        details: {
          attempt,
          nextAttemptInMs: resetDelay,
          maxAttempts: AUTO_RECOVERY_MAX_ATTEMPTS,
        },
      });

      this.circuitResetTimer = setTimeout(() => {
        this.state.circuitOpen = false;
        pushEvent({ type: "circuit_close", details: { trigger: "auto_reset" } });
        this.scheduleHealthCheck(1_000);
      }, resetDelay);
    } else {
      pushEvent({
        type: "auto_recovery",
        details: {
          attempt,
          message:
            "Max auto-recovery attempts reached. Manual intervention required.",
          maxAttempts: AUTO_RECOVERY_MAX_ATTEMPTS,
        },
      });
      this.notifyListeners();
    }
  }

  private closeCircuitBreaker() {
    if (!this.state.circuitOpen) return;
    this.state.circuitOpen = false;
    this.state.autoRecoveryAttempt = 0;
    if (this.circuitResetTimer !== null) {
      clearTimeout(this.circuitResetTimer);
      this.circuitResetTimer = null;
    }
    pushEvent({ type: "circuit_close", details: { trigger: "request_success" } });
  }

  private notifyListeners() {
    const snapshot = { ...this.state };
    for (const listener of this.listeners) {
      try {
        listener(snapshot.status, snapshot);
      } catch {
        // swallow listener errors
      }
    }
  }

  private scheduleHealthCheck(delayMs: number) {
    if (this.healthCheckTimer !== null) {
      clearTimeout(this.healthCheckTimer);
    }
    this.healthCheckTimer = setTimeout(() => {
      void this.performHealthCheck();
    }, delayMs);
  }

  private async performHealthCheck(): Promise<ConnectionStatus> {
    if (!this.configGetter) return this.state.status;
    if (this.state.circuitOpen) return this.state.status;

    const wasStable =
      this.state.status === "connected" || this.state.status === "degraded";
    if (!wasStable) {
      this.setStatus("checking");
    }

    const config = this.configGetter();
    const start = performance.now();

    try {
      const health = await apiClient.health(config);
      const latency = Math.round(performance.now() - start);

      this.state.latencyMs = latency;
      this.state.lastHealthCheckAt = new Date().toISOString();
      this.state.consecutiveFailures = 0;
      this.state.lastError = null;

      pushEvent({
        type: "health_check",
        latencyMs: latency,
      });

      if (health.db === "unavailable") {
        this.state.lastError = "database unavailable";
        this.setStatus("degraded");
      } else if (latency > DEGRADED_THRESHOLD_MS) {
        this.setStatus("degraded");
      } else {
        this.setStatus("connected");
      }

      this.scheduleHealthCheck(HEALTH_CHECK_INTERVAL_MS);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      const latency = Math.round(performance.now() - start);

      this.state.latencyMs = latency;
      this.state.lastHealthCheckAt = new Date().toISOString();
      this.state.consecutiveFailures++;
      this.state.lastError = message;

      pushEvent({
        type: "health_check",
        latencyMs: latency,
        error: message,
        details: { consecutiveFailures: this.state.consecutiveFailures },
      });

      if (wasStable && this.state.consecutiveFailures < 3) {
        this.setStatus("degraded");
      } else {
        this.setStatus("disconnected");
      }

      if (this.state.consecutiveFailures >= CIRCUIT_BREAKER_THRESHOLD) {
        this.openCircuitBreaker();
      } else {
        const backoff = Math.min(
          BACKOFF_BASE_MS *
            Math.pow(2, Math.min(this.state.consecutiveFailures - 1, 6)),
          MAX_BACKOFF_MS,
        );
        const jitter = Math.random() * 2_000;

        pushEvent({
          type: "recovery_attempt",
          details: {
            nextCheckInMs: backoff + jitter,
            consecutiveFailures: this.state.consecutiveFailures,
          },
        });

        this.scheduleHealthCheck(backoff + jitter);
      }
    }

    return this.state.status;
  }
}

export const connectionManager = new ConnectionManager();
