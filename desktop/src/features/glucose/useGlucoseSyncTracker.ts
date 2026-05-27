import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  apiClient,
  type GlucoseDashboardResponse,
  type GlucoseMode,
} from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useApiConfig } from "../settings/settingsStore";
import { glucoseSyncLogger } from "./glucoseSyncLogger";
import {
  CGM_INTERVAL_MS,
  MAX_CHECK_INTERVAL_MS,
  MIN_CHECK_INTERVAL_MS,
  POST_DETECTION_DELAY_MS,
  calculateBackoffMs,
  delayFromLatestReading,
  isSensorStreamDisconnected,
} from "./glucoseSyncTiming";

const MAX_CONSECUTIVE_ERRORS = 10;
const OFFLINE_AUTO_RECOVERY_MS = 2 * 60 * 1000;
const SYNC_LOOKBACK_HOURS = 6;
const SYNC_DASHBOARD_MODE: GlucoseMode = "raw";

export type SyncPhase =
  | "idle"
  | "checking"
  | "awaiting_data"
  | "importing"
  | "backing_off"
  | "sensor_disconnected"
  | "offline";

export interface SyncState {
  phase: SyncPhase;
  lastKnownReadingTs: string | null;
  lastSuccessfulImportAt: string | null;
  lastCheckAt: string | null;
  nextScheduledAt: Date | null;
  consecutiveErrors: number;
  currentSensorId: string | null;
  lastError: string | null;
}

interface SensorState {
  lastKnownReadingTs: string | null;
  lastSuccessfulImportAt: string | null;
  consecutiveErrors: number;
}

function extractLatestTimestamp(data: GlucoseDashboardResponse): string | null {
  const points = data.points;
  if (!points || points.length === 0) return null;
  const last = points[points.length - 1];
  return last.timestamp ?? null;
}

const pad = (value: number) => value.toString().padStart(2, "0");

const toLocalDateTimeSecond = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;

function currentSyncWindow() {
  const to = new Date();
  to.setSeconds(0, 0);
  const from = new Date(to.getTime() - SYNC_LOOKBACK_HOURS * 60 * 60 * 1000);
  return {
    from: toLocalDateTimeSecond(from),
    to: toLocalDateTimeSecond(to),
  };
}

export function useGlucoseSyncTracker(
  mode: GlucoseMode,
  enabled: boolean,
  nightscoutConfigured: boolean,
): {
  syncState: SyncState;
  forceRefresh: () => void;
  resetConnection: () => void;
  logSummary: typeof glucoseSyncLogger.summary;
  exportLog: typeof glucoseSyncLogger.exportLog;
};
export function useGlucoseSyncTracker(
  from: string,
  to: string,
  mode: GlucoseMode,
  enabled: boolean,
  nightscoutConfigured: boolean,
): {
  syncState: SyncState;
  forceRefresh: () => void;
  resetConnection: () => void;
  logSummary: typeof glucoseSyncLogger.summary;
  exportLog: typeof glucoseSyncLogger.exportLog;
};
export function useGlucoseSyncTracker(
  arg1: GlucoseMode | string,
  arg2: boolean | string,
  arg3: boolean | GlucoseMode,
  arg4?: boolean,
  arg5?: boolean,
) {
  const requestedMode =
    typeof arg2 === "string" ? (arg3 as GlucoseMode) : (arg1 as GlucoseMode);
  const enabled = typeof arg2 === "string" ? Boolean(arg4) : Boolean(arg2);
  const nightscoutConfigured =
    typeof arg2 === "string" ? Boolean(arg5) : Boolean(arg3);
  const config = useApiConfig();
  const queryClient = useQueryClient();

  const [syncState, setSyncState] = useState<SyncState>({
    phase: "idle",
    lastKnownReadingTs: null,
    lastSuccessfulImportAt: null,
    lastCheckAt: null,
    nextScheduledAt: null,
    consecutiveErrors: 0,
    currentSensorId: null,
    lastError: null,
  });

  const syncStateRef = useRef(syncState);
  const sensorStates = useRef<Map<string, SensorState>>(new Map());
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const importInProgressRef = useRef(false);
  const requestedModeRef = useRef(requestedMode);

  syncStateRef.current = syncState;
  requestedModeRef.current = requestedMode;

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const updateSensorState = useCallback(
    (sensorId: string, patch: Partial<SensorState>) => {
      const prev = sensorStates.current.get(sensorId) ?? {
        lastKnownReadingTs: null,
        lastSuccessfulImportAt: null,
        consecutiveErrors: 0,
      };
      sensorStates.current.set(sensorId, { ...prev, ...patch });
    },
    [],
  );

  const readCurrentDashboard = useCallback(async () => {
    const window = currentSyncWindow();
    return queryClient.fetchQuery({
      queryKey: queryKeys.glucoseDashboard(
        window.from,
        window.to,
        SYNC_DASHBOARD_MODE,
      ),
      queryFn: () =>
        apiClient.getGlucoseDashboard(
          config,
          window.from,
          window.to,
          SYNC_DASHBOARD_MODE,
        ),
      staleTime: 30_000,
    });
  }, [config, queryClient]);

  const performImport = useCallback(async () => {
    if (!mountedRef.current || importInProgressRef.current) return;
    importInProgressRef.current = true;

    const sensorId = syncStateRef.current.currentSensorId ?? "unknown";
    const importWindow = currentSyncWindow();

    setSyncState((prev) => ({ ...prev, phase: "importing", lastError: null }));
    glucoseSyncLogger.info("import_start", {
      sensorId,
      from: importWindow.from,
      to: importWindow.to,
    });

    try {
      const result = await apiClient.importNightscoutContext(config, {
        from_datetime: importWindow.from,
        to_datetime: importWindow.to,
        sync_glucose: true,
        import_insulin_events: true,
      });

      if (!mountedRef.current) return;

      const now = new Date().toISOString();
      const hadNewData = result.glucose_imported > 0;

      await queryClient.invalidateQueries({ queryKey: ["glucose"] });
      await queryClient.invalidateQueries({ queryKey: queryKeys.nightscoutLatestReading });
      await queryClient.invalidateQueries({ queryKey: ["timeline"] });

      const dashboardData = await readCurrentDashboard().catch(() => null);

      let latestTs: string | null = null;
      const currentSensorId = dashboardData?.current_sensor?.id ?? sensorId;
      if (dashboardData) {
        latestTs = extractLatestTimestamp(dashboardData);
      }

      updateSensorState(currentSensorId, {
        lastSuccessfulImportAt: now,
        consecutiveErrors: 0,
      });

      glucoseSyncLogger.info("import_success", {
        sensorId: currentSensorId,
        glucoseImported: result.glucose_imported,
        insulinImported: result.insulin_imported,
        hadNewData,
      });

      if (latestTs) {
        updateSensorState(currentSensorId, { lastKnownReadingTs: latestTs });

        const streamDisconnected = isSensorStreamDisconnected(latestTs);
        const delay = streamDisconnected
          ? MAX_CHECK_INTERVAL_MS
          : delayFromLatestReading(latestTs);

        glucoseSyncLogger.info(
          streamDisconnected
            ? "sensor_stream_disconnected"
            : hadNewData
              ? "schedule_next_after_new_data"
              : "schedule_next_from_local_latest",
          {
            sensorId: currentSensorId,
            latestTs,
            streamDisconnected,
            nextCheckInMs: delay,
          },
        );

        setSyncState((prev) => ({
          ...prev,
          phase: streamDisconnected ? "sensor_disconnected" : "awaiting_data",
          lastKnownReadingTs: latestTs,
          lastSuccessfulImportAt: now,
          lastCheckAt: now,
          currentSensorId,
          nextScheduledAt: new Date(Date.now() + delay),
          consecutiveErrors: 0,
          lastError: null,
        }));

        clearTimer();
        timerRef.current = setTimeout(() => {
          if (mountedRef.current) performImport();
        }, delay);
      } else {
        const delay = CGM_INTERVAL_MS + POST_DETECTION_DELAY_MS;

        glucoseSyncLogger.info("schedule_next_no_new_data", {
          sensorId: currentSensorId,
          nextCheckInMs: delay,
        });

        setSyncState((prev) => ({
          ...prev,
          phase: "awaiting_data",
          lastSuccessfulImportAt: now,
          lastCheckAt: now,
          currentSensorId,
          nextScheduledAt: new Date(Date.now() + delay),
          consecutiveErrors: 0,
          lastError: null,
        }));

        clearTimer();
        timerRef.current = setTimeout(() => {
          if (mountedRef.current) performImport();
        }, delay);
      }
    } catch (err: unknown) {
      if (!mountedRef.current) return;

      const message = err instanceof Error ? err.message : String(err);
      const errors = syncStateRef.current.consecutiveErrors + 1;

      updateSensorState(sensorId, { consecutiveErrors: errors });
      glucoseSyncLogger.error("import_failed", {
        sensorId,
        error: message,
        consecutiveErrors: errors,
      });

      if (errors >= MAX_CONSECUTIVE_ERRORS) {
        glucoseSyncLogger.error("max_errors_reached", { sensorId });
        setSyncState((prev) => ({
          ...prev,
          phase: "offline",
          consecutiveErrors: errors,
          lastError: message,
        }));

        glucoseSyncLogger.info("auto_recovery_scheduled", {
          sensorId,
          retryInMs: OFFLINE_AUTO_RECOVERY_MS,
        });
        clearTimer();
        timerRef.current = setTimeout(() => {
          if (mountedRef.current) {
            glucoseSyncLogger.info("auto_recovery_triggered", { sensorId });
            updateSensorState(sensorId, { consecutiveErrors: 0 });
            performImport();
          }
        }, OFFLINE_AUTO_RECOVERY_MS);
        return;
      }

      const backoff = calculateBackoffMs(errors);

      setSyncState((prev) => ({
        ...prev,
        phase: "backing_off",
        consecutiveErrors: errors,
        lastError: message,
        nextScheduledAt: new Date(Date.now() + backoff),
      }));

      clearTimer();
      timerRef.current = setTimeout(() => {
        if (mountedRef.current) performImport();
      }, backoff);
    } finally {
      importInProgressRef.current = false;
    }
  }, [
    config,
    queryClient,
    clearTimer,
    updateSensorState,
    readCurrentDashboard,
  ]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimer();
    };
  }, [clearTimer]);

  useEffect(() => {
    if (!enabled || !nightscoutConfigured) {
      clearTimer();
      setSyncState((prev) => ({
        ...prev,
        phase: "idle",
        nextScheduledAt: null,
      }));
      glucoseSyncLogger.info("sync_disabled");
      return;
    }

    const dashboardWindow = currentSyncWindow();
    glucoseSyncLogger.info("sync_enabled", {
      from: dashboardWindow.from,
      to: dashboardWindow.to,
      displayMode: requestedModeRef.current,
      syncMode: SYNC_DASHBOARD_MODE,
    });

    const dashboardData = queryClient.getQueryData<GlucoseDashboardResponse>(
      queryKeys.glucoseDashboard(
        dashboardWindow.from,
        dashboardWindow.to,
        SYNC_DASHBOARD_MODE,
      ),
    );

    if (dashboardData) {
      const latestTs = extractLatestTimestamp(dashboardData);
      const sensorId = dashboardData.current_sensor?.id ?? "unknown";

      if (latestTs) {
        const streamDisconnected = isSensorStreamDisconnected(latestTs);
        const delay = streamDisconnected
          ? MIN_CHECK_INTERVAL_MS
          : delayFromLatestReading(latestTs);

        updateSensorState(sensorId, { lastKnownReadingTs: latestTs });
        glucoseSyncLogger.info("initial_schedule_from_cache", {
          sensorId,
          latestTs,
          streamDisconnected,
          nextCheckInMs: delay,
        });

        setSyncState((prev) => ({
          ...prev,
          phase: streamDisconnected ? "sensor_disconnected" : "awaiting_data",
          lastKnownReadingTs: latestTs,
          currentSensorId: sensorId,
          nextScheduledAt: new Date(Date.now() + delay),
        }));

        clearTimer();
        timerRef.current = setTimeout(() => {
          if (mountedRef.current) performImport();
        }, delay);
      } else {
        const initialDelay = POST_DETECTION_DELAY_MS;
        setSyncState((prev) => ({
          ...prev,
          phase: "checking",
          currentSensorId: sensorId,
          nextScheduledAt: new Date(Date.now() + initialDelay),
        }));
        clearTimer();
        timerRef.current = setTimeout(() => {
          if (mountedRef.current) performImport();
        }, initialDelay);
      }
    } else {
      const initialDelay = 2000;
      setSyncState((prev) => ({
        ...prev,
        phase: "checking",
        nextScheduledAt: new Date(Date.now() + initialDelay),
      }));
      clearTimer();
      timerRef.current = setTimeout(() => {
        if (mountedRef.current) performImport();
      }, initialDelay);
    }

    return () => {
      clearTimer();
    };
  }, [
    clearTimer,
    enabled,
    nightscoutConfigured,
    performImport,
    queryClient,
    updateSensorState,
  ]);

  useEffect(() => {
    const currentSensorId = syncState.currentSensorId;
    if (!currentSensorId) return;

    const sensorState = sensorStates.current.get(currentSensorId);
    if (!sensorState) return;

    if (sensorState.consecutiveErrors >= 3) {
      glucoseSyncLogger.warn("sensor_errors_accumulated", {
        sensorId: currentSensorId,
        errors: sensorState.consecutiveErrors,
      });
    }
  }, [syncState.consecutiveErrors, syncState.currentSensorId]);

  const forceRefresh = useCallback(() => {
    if (importInProgressRef.current) return;
    glucoseSyncLogger.info("force_refresh");
    clearTimer();
    performImport();
  }, [clearTimer, performImport]);

  const resetConnection = useCallback(() => {
    glucoseSyncLogger.info("reset_connection");
    if (syncState.currentSensorId) {
      updateSensorState(syncState.currentSensorId, { consecutiveErrors: 0 });
    }
    setSyncState((prev) => ({
      ...prev,
      phase: "idle",
      consecutiveErrors: 0,
      lastError: null,
    }));
    clearTimer();
    setTimeout(() => {
      if (mountedRef.current) performImport();
    }, 500);
  }, [clearTimer, performImport, syncState.currentSensorId, updateSensorState]);

  return {
    syncState,
    forceRefresh,
    resetConnection,
    logSummary: glucoseSyncLogger.summary,
    exportLog: glucoseSyncLogger.exportLog,
  };
}
