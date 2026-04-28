import {
  apiClient,
  type ApiConfig,
  type MealItemCreate,
  type MealResponse,
} from "../../api/client";
import {
  localDateBoundaryString,
  localDateTimeBefore,
  toLocalDateTimeString,
} from "../../utils/dateTime";

export const FEED_PAGE_SIZE = 50;

export type FeedStatusFilter = "active" | "accepted" | "draft" | "discarded";

export type FeedFilters = {
  from: string;
  q: string;
  status: FeedStatusFilter;
  to: string;
};

export const buildFeedMealQuery = (filters: FeedFilters, cursor?: string) => ({
  from: localDateBoundaryString(filters.from, false),
  limit: FEED_PAGE_SIZE,
  q: filters.q.trim() || undefined,
  status: filters.status === "active" ? undefined : filters.status,
  to: cursor ?? localDateBoundaryString(filters.to, true),
});

export const nextCursorBefore = (meal: MealResponse) =>
  localDateTimeBefore(meal.eaten_at);

const responseItemToCreate = (
  item: NonNullable<MealResponse["items"]>[number],
): MealItemCreate => ({
  assumptions: item.assumptions ?? [],
  brand: item.brand,
  calculation_method: item.calculation_method,
  carbs_g: item.carbs_g,
  confidence: item.confidence,
  confidence_reason: item.confidence_reason,
  evidence: item.evidence ?? {},
  fat_g: item.fat_g,
  fiber_g: item.fiber_g,
  grams: item.grams,
  kcal: item.kcal,
  name: item.name,
  pattern_id: item.pattern_id,
  photo_id: null,
  position: item.position,
  product_id: item.product_id,
  protein_g: item.protein_g,
  serving_text: item.serving_text,
  source_kind: item.source_kind,
  warnings: item.warnings ?? [],
});

export async function duplicateMeal(
  config: ApiConfig,
  meal: MealResponse,
): Promise<MealResponse> {
  // TODO: Replace this POST-copy fallback with a backend duplicate endpoint.
  return apiClient.createMeal(config, {
    eaten_at: toLocalDateTimeString(new Date()),
    items: meal.items?.map(responseItemToCreate) ?? [],
    note: meal.note,
    source: meal.source,
    status: "accepted",
    title: meal.title,
  });
}
