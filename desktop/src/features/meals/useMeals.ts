import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { toLocalDateTimeString } from "../../utils/dateTime";
import { useApiConfig } from "../settings/settingsStore";

const startOfLocalDay = (date: Date) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate());

const addDays = (date: Date, days: number) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);

export function useMeals() {
  const config = useApiConfig();

  return useQuery({
    queryKey: queryKeys.meals({ limit: 20, offset: 0 }),
    queryFn: () => apiClient.listMeals(config, { limit: 20, offset: 0 }),
    enabled: Boolean(config.token.trim()),
  });
}

export function useTodayMeals() {
  const config = useApiConfig();
  const start = toLocalDateTimeString(startOfLocalDay(new Date()));
  const end = toLocalDateTimeString(addDays(new Date(), 1));

  return useQuery({
    queryKey: queryKeys.meals({ from: start, to: end, limit: 100, offset: 0 }),
    queryFn: async () => {
      const page = await apiClient.listMeals(config, {
        from: start,
        to: end,
        limit: 100,
        offset: 0,
      });
      return {
        ...page,
        items: page.items.filter((meal) => meal.status !== "discarded"),
      };
    },
    enabled: Boolean(config.token.trim()),
  });
}
