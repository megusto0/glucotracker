import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  apiClient,
  type FingerstickReadingCreate,
  type FingerstickReadingPatch,
  type GlucoseMode,
  type GlucosePredictionMode,
  type NightscoutLatestReadingResponse,
  type SensorSessionCreate,
  type SensorSessionPatch,
} from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useApiConfig } from "../settings/settingsStore";

export function useGlucoseDashboard(from: string, to: string, mode: GlucoseMode) {
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
    mutationFn: (payload: { body: FingerstickReadingPatch; fingerstickId: string }) =>
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
