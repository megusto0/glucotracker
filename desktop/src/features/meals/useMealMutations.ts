import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  apiClient,
  type ApiConfig,
  type MealItemCreate,
  type MealResponse,
} from "../../api/client";
import { useApiConfig } from "../settings/settingsStore";

type MealItem = NonNullable<MealResponse["items"]>[number];

const isRememberableLabelItem = (item: MealItem) =>
  item.source_kind === "label_calc" ||
  (item.calculation_method ?? "").startsWith("label_");

const MEAL_INVALIDATION_KEYS = [
  ["meals"],
  ["feed-meals"],
  ["dashboard"],
  ["autocomplete"],
  ["database"],
  ["database-items"],
] as const;

export function useUpdateMealTime() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ eatenAt, mealId }: { eatenAt: string; mealId: string }) =>
      apiClient.updateMeal(config, mealId, { eaten_at: eatenAt }),
    onSuccess: () => {
      MEAL_INVALIDATION_KEYS.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });
    },
  });
}

export function useUpdateMealName() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ meal, name }: { meal: MealResponse; name: string }) => {
      const updatedMeal = await apiClient.updateMeal(config, meal.id, {
        title: name,
      });
      const onlyItem = meal.items?.length === 1 ? meal.items[0] : null;
      if (onlyItem) {
        await apiClient.updateMealItem(config, onlyItem.id, { name });
        if (onlyItem.product_id) {
          await apiClient.updateProduct(config, onlyItem.product_id, { name });
        } else if (isRememberableLabelItem(onlyItem)) {
          const product = await apiClient.rememberProductFromMealItem(
            config,
            onlyItem.id,
            [],
          );
          await apiClient.updateProduct(config, product.id, { name });
        }
      }
      return updatedMeal;
    },
    onSuccess: () => {
      MEAL_INVALIDATION_KEYS.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: key });
      });
    },
  });
}

export function useDuplicateMeal() {
  const config = useApiConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (meal: MealResponse) => duplicateMeal(config, meal),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
      queryClient.invalidateQueries({ queryKey: ["meals"] });
    },
  });
}

const mealItemToCreate = (item: MealItem, position: number): MealItemCreate => ({
  name: item.name,
  brand: item.brand,
  grams: item.grams,
  serving_text: item.serving_text,
  carbs_g: item.carbs_g,
  protein_g: item.protein_g,
  fat_g: item.fat_g,
  fiber_g: item.fiber_g,
  kcal: item.kcal,
  confidence: item.confidence,
  confidence_reason: item.confidence_reason,
  source_kind: item.source_kind,
  calculation_method: item.calculation_method,
  assumptions: item.assumptions ?? [],
  evidence: item.evidence ?? {},
  warnings: item.warnings ?? [],
  pattern_id: item.pattern_id,
  product_id: item.product_id,
  photo_id: item.photo_id,
  position,
});

async function duplicateMeal(config: ApiConfig, meal: MealResponse): Promise<MealResponse> {
  const items = (meal.items ?? []).map((item, index) =>
    mealItemToCreate(item, index),
  );
  const now = new Date();
  const pad = (v: number) => v.toString().padStart(2, "0");
  const eatenAt = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  return apiClient.createMeal(config, {
    eaten_at: eatenAt,
    items,
    note: meal.note,
    source: meal.source,
    status: "accepted",
    title: meal.title,
  });
}
