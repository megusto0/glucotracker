import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient, apiRuntimeName } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useApiConfig } from "./settingsStore";

const formatDate = (date: Date) => date.toISOString().slice(0, 10);

export function useConnectionTest() {
  const config = useApiConfig();

  return useMutation({
    mutationFn: async () => {
      const health = await apiClient.health(config);
      let openapiAvailable = false;
      try {
        const openapi = await apiClient.openapi(config);
        openapiAvailable = Boolean(openapi.openapi);
      } catch {
        openapiAvailable = false;
      }
      return {
        health,
        openapiAvailable,
        runtime: apiRuntimeName(),
      };
    },
  });
}

export function useNightscoutStatus() {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.nightscoutStatus,
    queryFn: () => apiClient.getNightscoutStatus(config),
    enabled: Boolean(config.token.trim()),
  });
}

export function useRecalculateTotals() {
  const config = useApiConfig();

  return useMutation({
    mutationFn: () => {
      const now = new Date();
      const firstDay = new Date(
        Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1),
      );
      const lastDay = new Date(
        Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0),
      );
      return apiClient.adminRecalculate(
        config,
        formatDate(firstDay),
        formatDate(lastDay),
      );
    },
  });
}
