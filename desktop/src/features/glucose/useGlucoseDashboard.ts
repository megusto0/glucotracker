import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import {
  apiClient,
  type BasalFastingTestStartRequest,
  type BasalFastingTestStopRequest,
  type FingerstickReadingCreate,
  type FingerstickReadingPatch,
  type GlucoseMode,
  type GlucosePredictionMode,
  type InsulinRecommendationRequest,
  type NightscoutLatestReadingResponse,
  type NightscoutInsulinEntryCreate,
  type SensorSessionCreate,
  type SensorSessionPatch,
  type TherapyReviewDayResponse,
} from "../../api/client";
import {
  readPersistedQuery,
  writePersistedQuery,
} from "../../api/persistentQueryCache";
import { queryKeys } from "../../api/queryKeys";
import { useApiConfig } from "../settings/settingsStore";

export function useGlucoseDashboard(
  from: string,
  to: string,
  mode: GlucoseMode,
) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.glucoseDashboard(from, to, mode),
    queryFn: () => apiClient.getGlucoseDashboard(config, from, to, mode),
    enabled: Boolean(config.token.trim() && from && to),
    gcTime: 30 * 60 * 1000,
    placeholderData: (previousData) => previousData,
    staleTime: 5 * 60 * 1000,
  });
}

export function useHeartRateSeries(
  from: string,
  to: string,
  binMinutes = 10,
) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.heartRateSeries(from, to, binMinutes),
    queryFn: () =>
      apiClient.getHeartRateSeries(config, from, to, binMinutes),
    enabled: Boolean(config.token.trim() && from && to),
    gcTime: 30 * 60 * 1000,
    placeholderData: (previousData) => previousData,
    staleTime: 5 * 60 * 1000,
  });
}

export function useGlucosePrediction(mode: GlucosePredictionMode) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.glucosePrediction(mode),
    queryFn: () => apiClient.getGlucosePrediction(config, mode),
    enabled: Boolean(config.token.trim()),
    gcTime: 30 * 60 * 1000,
    placeholderData: (previousData) => previousData,
    refetchInterval: 60 * 1000,
    refetchOnWindowFocus: "always",
    retry: 1,
    staleTime: 30 * 1000,
  });
}

export function useGlucoseEpisodes(from: string, to: string) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.glucoseEpisodes(from, to),
    queryFn: () => apiClient.getGlucoseEpisodes(config, from, to),
    enabled: Boolean(config.token.trim() && from && to),
    staleTime: 30 * 1000,
  });
}

/** A closed day never changes once the backend agrees it is settled. */
const THERAPY_REVIEW_STALE_MS = 5 * 60 * 1000;

export function useGlucoseTherapyReview(
  date: string,
  targetMmolL: number,
  horizonMinutes: number,
) {
  const config = useApiConfig();
  const queryKey = queryKeys.glucoseTherapyReview(
    date,
    targetMmolL,
    horizonMinutes,
  );
  // Rebuilding a day costs the backend seconds, so a day that has already been
  // looked at is read straight off disk and revalidated in the background
  // rather than being waited for again after every reload.
  const persisted = useMemo(
    () => readPersistedQuery<TherapyReviewDayResponse>(queryKey),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [date, targetMmolL, horizonMinutes],
  );

  return useQuery({
    queryKey,
    queryFn: async () => {
      const data = await apiClient.getGlucoseTherapyReview(
        config,
        date,
        targetMmolL,
        horizonMinutes,
      );
      writePersistedQuery(queryKey, data);
      return data;
    },
    enabled: Boolean(
      config.token.trim() &&
      date &&
      Number.isFinite(targetMmolL) &&
      horizonMinutes,
    ),
    gcTime: 30 * 60 * 1000,
    initialData: persisted?.data,
    initialDataUpdatedAt: persisted?.updatedAt,
    // Deliberately no placeholder from the previous day: one day's episodes
    // shown under another day's heading is worse than a moment of waiting,
    // and prefetching the neighbours makes that moment rare.
    retry: 1,
    staleTime: THERAPY_REVIEW_STALE_MS,
  });
}

/**
 * Warm the days on either side of the one being read.
 *
 * Stepping through days is how this page is used, and the day the user is
 * about to ask for is exactly the one the backend has not computed yet.
 */
export function usePrefetchGlucoseTherapyReview() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useCallback(
    (dates: string[], targetMmolL: number, horizonMinutes: number) => {
      if (!config.token.trim()) return;
      for (const date of dates) {
        if (!date) continue;
        const queryKey = queryKeys.glucoseTherapyReview(
          date,
          targetMmolL,
          horizonMinutes,
        );
        if (queryClient.getQueryData(queryKey) !== undefined) continue;
        const persisted = readPersistedQuery<TherapyReviewDayResponse>(queryKey);
        if (persisted) {
          queryClient.setQueryData(queryKey, persisted.data, {
            updatedAt: persisted.updatedAt,
          });
          if (Date.now() - persisted.updatedAt < THERAPY_REVIEW_STALE_MS) {
            continue;
          }
        }
        void queryClient.prefetchQuery({
          queryKey,
          queryFn: async () => {
            const data = await apiClient.getGlucoseTherapyReview(
              config,
              date,
              targetMmolL,
              horizonMinutes,
            );
            writePersistedQuery(queryKey, data);
            return data;
          },
          staleTime: THERAPY_REVIEW_STALE_MS,
        });
      }
    },
    [config, queryClient],
  );
}

export function useRecalculateGlucoseTherapyReview() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      date,
      targetMmolL,
      horizonMinutes,
    }: {
      date: string;
      targetMmolL: number;
      horizonMinutes: number;
    }) =>
      apiClient.getGlucoseTherapyReview(
        config,
        date,
        targetMmolL,
        horizonMinutes,
        true,
      ),
    onSuccess: (data, variables) => {
      const queryKey = queryKeys.glucoseTherapyReview(
        variables.date,
        variables.targetMmolL,
        variables.horizonMinutes,
      );
      queryClient.setQueryData(queryKey, data);
      writePersistedQuery(queryKey, data);
    },
  });
}

export function useGlucoseBodyStates(from: string, to: string) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.glucoseBodyStates(from, to),
    queryFn: () => apiClient.getGlucoseBodyStates(config, from, to),
    enabled: Boolean(config.token.trim() && from && to),
    gcTime: 30 * 60 * 1000,
    placeholderData: (previousData) => previousData,
    retry: 1,
    staleTime: 5 * 60 * 1000,
  });
}

export function useGlucoseTherapyAnalysis(
  periodDays: 30 | 90 | 180,
  targetMmolL: number,
) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.glucoseTherapyAnalysis(periodDays, targetMmolL),
    queryFn: () =>
      apiClient.getGlucoseTherapyAnalysis(
        config,
        periodDays,
        targetMmolL,
      ),
    enabled: Boolean(
      config.token.trim() && Number.isFinite(targetMmolL),
    ),
    gcTime: 60 * 60 * 1000,
    retry: 1,
    staleTime: 30 * 60 * 1000,
  });
}

export function useBasalFastingTests() {
  const config = useApiConfig();
  return useQuery({
    queryFn: () => apiClient.listBasalFastingTests(config),
    queryKey: ["basal-fasting-tests"],
    // A run is a clock the owner is watching, so a stale card is worse than a
    // refetch; the outcome is recomputed from CGM on every read anyway.
    refetchInterval: 60_000,
  });
}

export function useStartBasalFastingTest() {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: BasalFastingTestStartRequest) =>
      apiClient.startBasalFastingTest(config, body),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["basal-fasting-tests"] }),
  });
}

export function useStopBasalFastingTest() {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      runId: string;
      body: BasalFastingTestStopRequest;
    }) => apiClient.stopBasalFastingTest(config, input.runId, input.body),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["basal-fasting-tests"] }),
  });
}

export function useTopUpDose(targetMmolL: number | undefined, enabled: boolean) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.topUpDose(targetMmolL),
    queryFn: () => apiClient.getTopUpDose(config, targetMmolL),
    // Only fetched when the user asks: the answer depends on IOB and COB right
    // now, so a stale one is worse than none.
    enabled: Boolean(config.token.trim()) && enabled,
    retry: 1,
    refetchInterval: enabled ? 60_000 : false,
    gcTime: 0,
    staleTime: 0,
  });
}

export function useInsulinRecommendation(
  mealIds: string[],
  correctionTarget?: number,
) {
  const config = useApiConfig();
  const normalizedIds = [...new Set(mealIds)];

  return useQuery({
    queryKey: queryKeys.insulinRecommendation(normalizedIds, correctionTarget),
    queryFn: () =>
      apiClient.getInsulinRecommendation(config, {
        meal_ids: normalizedIds,
        correction_target_mmol_l: correctionTarget,
      } satisfies InsulinRecommendationRequest),
    enabled: Boolean(config.token.trim() && normalizedIds.length),
    retry: 1,
    staleTime: 30 * 1000,
  });
}

export function useCreateNightscoutInsulin() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: NightscoutInsulinEntryCreate) =>
      apiClient.createNightscoutInsulin(config, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["glucose"] });
      void queryClient.invalidateQueries({ queryKey: ["nightscout"] });
    },
  });
}

export function useDeleteNightscoutInsulin() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (eventId: string) =>
      apiClient.deleteNightscoutInsulin(config, eventId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["glucose"] });
      void queryClient.invalidateQueries({ queryKey: ["nightscout"] });
    },
  });
}

export function useLatestGlucoseReading() {
  const config = useApiConfig();

  return useQuery<NightscoutLatestReadingResponse>({
    queryKey: queryKeys.nightscoutLatestReading,
    queryFn: () => apiClient.getNightscoutLatestReading(config),
    enabled: Boolean(config.token.trim()),
    gcTime: 30 * 60 * 1000,
    staleTime: 30 * 1000,
  });
}

export function useSensors() {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.sensors,
    queryFn: () => apiClient.listSensors(config),
    enabled: Boolean(config.token.trim()),
  });
}

export function useCreateFingerstick() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: FingerstickReadingCreate) =>
      apiClient.createFingerstick(config, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["glucose"] });
    },
  });
}

export function useUpdateFingerstick() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      body: FingerstickReadingPatch;
      fingerstickId: string;
    }) =>
      apiClient.patchFingerstick(config, payload.fingerstickId, payload.body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["glucose"] });
    },
  });
}

export function useDeleteFingerstick() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (fingerstickId: string) =>
      apiClient.deleteFingerstick(config, fingerstickId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["glucose"] });
    },
  });
}

export function useSaveSensor() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      body: SensorSessionCreate | SensorSessionPatch;
      sensorId?: string;
    }) =>
      payload.sensorId
        ? apiClient.patchSensor(config, payload.sensorId, payload.body)
        : apiClient.createSensor(config, payload.body as SensorSessionCreate),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["glucose"] });
    },
  });
}

export function useRecalculateSensorCalibration() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (sensorId: string) =>
      apiClient.recalculateSensorCalibration(config, sensorId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["glucose"] });
    },
  });
}
