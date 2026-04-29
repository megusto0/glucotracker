import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, type NightscoutSettingsPatch } from "../../api/client";
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
