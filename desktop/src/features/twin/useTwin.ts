import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, type TwinParamsPatch } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useApiConfig } from "../settings/settingsStore";

export function useTwinParams() {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.twinParams,
    queryFn: () => apiClient.getTwinParams(config),
    enabled: Boolean(config.token.trim()),
    staleTime: 60_000,
  });
}

export function useTwinCurve(from: string, to: string, stepMinutes = 5) {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.twinCurve(from, to, stepMinutes),
    queryFn: () => apiClient.getTwinCurve(config, from, to, stepMinutes),
    enabled: Boolean(config.token.trim() && from && to),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
}

export function useResetTwinParams() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => apiClient.resetTwinParams(config),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["twin"] });
    },
  });
}

export function usePatchTwinParams() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: TwinParamsPatch) => apiClient.patchTwinParams(config, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["twin"] });
    },
  });
}
