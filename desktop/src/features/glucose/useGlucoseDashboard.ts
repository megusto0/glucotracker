import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  apiClient,
  type FingerstickReadingCreate,
  type FingerstickReadingPatch,
  type GlucoseMode,
  type GlucosePredictionMode,
  type InsulinRecommendationRequest,
  type NightscoutLatestReadingResponse,
  type NightscoutInsulinEntryCreate,
  type SensorSessionCreate,
  type SensorSessionPatch,
} from "../../api/client";
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
