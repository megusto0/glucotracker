import { describe, expect, test } from "vitest";
import type { MealResponse } from "../api/client";
import { buildFoodDiaryTextReport } from "../utils/mealTextReport";

type MealItemResponse = NonNullable<MealResponse["items"]>[number];

const meal = (overrides: Partial<MealResponse>): MealResponse =>
  ({
    confidence: null,
    created_at: "2026-04-28T10:00:00",
    eaten_at: "2026-04-28T10:00:00",
    id: "meal-1",
    items: [],
    nightscout_id: null,
    nightscout_last_attempt_at: null,
    nightscout_sync_error: null,
    nightscout_sync_status: "not_synced",
    nightscout_synced_at: null,
    note: null,
    photos: [],
    source: "manual",
    status: "accepted",
    thumbnail_url: null,
    title: "Тест",
    total_carbs_g: 0,
    total_fat_g: 0,
    total_fiber_g: 0,
    total_kcal: 0,
    total_protein_g: 0,
    updated_at: "2026-04-28T10:00:00",
    ...overrides,
  }) as MealResponse;

describe("buildFoodDiaryTextReport", () => {
  test("groups accepted meals by all days with entries and includes totals", () => {
    const text = buildFoodDiaryTextReport([
      meal({
        eaten_at: "2026-04-29T12:00:00",
        id: "meal-2",
        title: "Обед",
        total_carbs_g: 20,
        total_fat_g: 5,
        total_fiber_g: 2,
        total_kcal: 150,
        total_protein_g: 10,
      }),
      meal({
        eaten_at: "2026-04-28T09:00:00",
        items: [
          {
            assumptions: [],
            brand: "Brand",
            calculation_method: null,
            carbs_g: 12.5,
            confidence: null,
            confidence_reason: null,
            created_at: "2026-04-28T09:00:00",
            evidence: {},
            fat_g: 3,
            fiber_g: 1,
            grams: 100,
            id: "item-1",
            kcal: 88,
            meal_id: "meal-1",
            name: "Йогурт",
            nutrients: [],
            pattern_id: null,
            photo_id: null,
            position: 0,
            product_id: null,
            protein_g: 4,
            serving_text: "100 г",
            source_kind: "manual",
            updated_at: "2026-04-28T09:00:00",
            warnings: [],
          } satisfies MealItemResponse,
        ],
        title: "Завтрак",
        total_carbs_g: 12.5,
        total_fat_g: 3,
        total_fiber_g: 1,
        total_kcal: 88,
        total_protein_g: 4,
      }),
      meal({
        eaten_at: "2026-04-28T10:00:00",
        id: "discarded",
        status: "discarded",
        title: "Не включать",
        total_carbs_g: 100,
      }),
    ]);

    expect(text).toContain("## 28 апреля 2026");
    expect(text).toContain("## 29 апреля 2026");
    expect(text).toContain(
      "Итого за день: углеводы 12.5 г; белки 4 г; жиры 3 г; клетчатка 1 г; ккал 88",
    );
    expect(text).toContain("09:00 — Завтрак");
    expect(text).toContain(
      "- Йогурт — Brand (100 г): углеводы 12.5 г; белки 4 г; жиры 3 г; клетчатка 1 г; ккал 88",
    );
    expect(text).toContain("Углеводы: 32.5 г");
    expect(text).not.toContain("Не включать");
  });
});
