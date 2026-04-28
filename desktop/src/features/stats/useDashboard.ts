import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useApiConfig } from "../settings/settingsStore";

const dateKey = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(
    2,
    "0",
  )}-${String(date.getDate()).padStart(2, "0")}`;

const addDays = (date: Date, days: number) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);

export const defaultDashboardRange = () => {
  const today = new Date();
  return {
    from: dateKey(addDays(today, -29)),
    to: dateKey(today),
  };
};

export function useDashboardToday() {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.dashboardToday,
    queryFn: () => apiClient.getDashboardToday(config),
    enabled: Boolean(config.token.trim()),
  });
}

export function useDashboardRange(from: string, to: string) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.dashboardRange(from, to),
    queryFn: () => apiClient.getDashboardRange(config, from, to),
    enabled: Boolean(config.token.trim() && from && to),
  });
}

export function useDashboardHeatmap(weeks = 4) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.dashboardHeatmap(weeks),
    queryFn: () => apiClient.getDashboardHeatmap(config, weeks),
    enabled: Boolean(config.token.trim()),
  });
}

export function useDashboardTopPatterns(days = 7, limit = 10) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.dashboardTopPatterns(days, limit),
    queryFn: () => apiClient.getDashboardTopPatterns(config, days, limit),
    enabled: Boolean(config.token.trim()),
  });
}

export function useDashboardSourceBreakdown(days = 7) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.dashboardSourceBreakdown(days),
    queryFn: () => apiClient.getDashboardSourceBreakdown(config, days),
    enabled: Boolean(config.token.trim()),
  });
}

export function useDashboardDataQuality(days = 7) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.dashboardDataQuality(days),
    queryFn: () => apiClient.getDashboardDataQuality(config, days),
    enabled: Boolean(config.token.trim()),
  });
}
