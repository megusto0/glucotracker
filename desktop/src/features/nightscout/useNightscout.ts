import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  apiClient,
  type NightscoutImportRequest,
  type NightscoutSettingsPatch,
} from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useApiConfig } from "../settings/settingsStore";

export const localDateKey = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")}`;

export function useNightscoutSettings() {
  const config = useApiConfig();
  return useQuery({
    queryKey: queryKeys.nightscoutSettings,
    queryFn: () => apiClient.getNightscoutSettings(config),
    enabled: Boolean(config.token.trim()),
  });
}

export function useUpdateNightscoutSettings() {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: NightscoutSettingsPatch) =>
      apiClient.updateNightscoutSettings(config, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.nightscoutSettings });
      queryClient.invalidateQueries({ queryKey: queryKeys.nightscoutStatus });
    },
  });
}

export function useTestNightscoutConnection() {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.testNightscoutConnection(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.nightscoutSettings });
      queryClient.invalidateQueries({ queryKey: queryKeys.nightscoutStatus });
    },
  });
}

export function useNightscoutDayStatus(date: string) {
  const config = useApiConfig();
  return useQuery({
    queryKey: queryKeys.nightscoutDayStatus(date),
    queryFn: () => apiClient.getNightscoutDayStatus(config, date),
    enabled: Boolean(config.token.trim()),
  });
}

export function useSyncTodayToNightscout(date: string) {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.syncTodayToNightscout(config, date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meals"] });
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.nightscoutDayStatus(date) });
    },
  });
}

export function useSyncMealToNightscout(date?: string) {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mealId: string) => apiClient.syncMealToNightscout(config, mealId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meals"] });
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
      if (date) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.nightscoutDayStatus(date),
        });
      }
    },
  });
}

export function useResyncMealToNightscout(date?: string) {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (mealId: string) => {
      await apiClient.unsyncMealFromNightscout(config, mealId);
      return apiClient.syncMealToNightscout(config, mealId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meals"] });
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
      if (date) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.nightscoutDayStatus(date),
        });
      }
    },
  });
}

export function useNightscoutEvents(from: string, to: string, enabled: boolean) {
  const config = useApiConfig();
  return useQuery({
    queryKey: queryKeys.nightscoutEvents(from, to),
    queryFn: () => apiClient.getNightscoutEvents(config, from, to),
    enabled: Boolean(config.token.trim()) && enabled,
  });
}

export function useImportNightscoutContext(from: string, to: string) {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload?: Partial<NightscoutImportRequest>) =>
      apiClient.importNightscoutContext(config, {
        from_datetime: payload?.from_datetime ?? from,
        to_datetime: payload?.to_datetime ?? to,
        sync_glucose: payload?.sync_glucose ?? true,
        import_insulin_events: payload?.import_insulin_events ?? true,
      }),
    onSuccess: (result) => {
      const resultFrom = result.from_datetime ?? from;
      const resultTo = result.to_datetime ?? to;
      queryClient.invalidateQueries({
        queryKey: queryKeys.timeline(resultFrom, resultTo),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.nightscoutEvents(resultFrom, resultTo),
      });
      queryClient.invalidateQueries({ queryKey: ["glucose"] });
    },
  });
}

export function useTimeline(from: string, to: string, enabled: boolean) {
  const config = useApiConfig();
  return useQuery({
    queryKey: queryKeys.timeline(from, to),
    queryFn: () => apiClient.getTimeline(config, from, to),
    enabled: Boolean(config.token.trim()) && enabled,
    staleTime: 5 * 60 * 1000,
  });
}
