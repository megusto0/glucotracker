import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../../api/client";
import { useApiConfig } from "../settings/settingsStore";
import type { components } from "../../api/generated/schema";

type AutocompleteSuggestion = components["schemas"]["AutocompleteSuggestion"];

export function useAutocomplete(query: string) {
  const config = useApiConfig();

  return useQuery({
    queryKey: ["autocomplete", query],
    queryFn: () =>
      apiRequest<AutocompleteSuggestion[]>("/autocomplete", config, {
        query: { q: query, limit: 20 },
      }),
    enabled: Boolean(config.token.trim() && query.trim()),
  });
}
