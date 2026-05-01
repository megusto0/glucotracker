import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  apiClient,
  type FingerstickReadingCreate,
  type FingerstickReadingPatch,
  type GlucoseMode,
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
