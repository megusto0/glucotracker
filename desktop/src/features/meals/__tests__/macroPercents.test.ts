import type { MealResponse } from "../../../api/client";
import { macroPercentsOfDailyNorm } from "../MealLedger";

function makeMeal(overrides: Partial<MealResponse> = {}): MealResponse {
  const { nightscout_sync_status, ...mealOverrides } = overrides;
  return {
    id: "meal-1",
    eaten_at: "2026-05-01T10:00:00.000Z",
    title: "Тест",
    note: null,
    status: "accepted",
    source: "manual",
    total_carbs_g: 45,
    total_protein_g: 24,
    total_fat_g: 16,
    total_fiber_g: 6,
    total_kcal: 540,
    confidence: null,
    nightscout_synced_at: null,
    nightscout_id: null,
    created_at: "2026-05-01T10:00:00.000Z",
    updated_at: "2026-05-01T10:00:00.000Z",
    items: [],
    photos: [],
    thumbnail_url: null,
    ...mealOverrides,
    nightscout_sync_status: nightscout_sync_status ?? "not_synced",
  };
}

test("считает проценты макросов от дневной нормы", () => {
  const percents = macroPercentsOfDailyNorm(makeMeal());

  expect(percents).toEqual({
    carbs: 20,
    protein: 20,
    fat: 20,
    fiber: 20,
  });
});

test("округляет проценты до целого", () => {
  const percents = macroPercentsOfDailyNorm(
    makeMeal({
      total_carbs_g: 62,
      total_protein_g: 31,
      total_fat_g: 26,
      total_fiber_g: 11,
    }),
  );

  expect(percents).toEqual({
    carbs: 28,
    protein: 26,
    fat: 33,
    fiber: 37,
  });
});
