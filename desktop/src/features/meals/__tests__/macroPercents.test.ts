import type { MealResponse } from "../../../api/client";
import {
  favoriteProductPayload,
  macroPercentsOfDailyNorm,
  mealQuantityInfo,
} from "../MealLedger";

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

test("favorite product payload stores one unit from multi-unit meal", () => {
  const meal = makeMeal({
    title: "Тако с курицей и овощами ×2",
    total_carbs_g: 70.3,
    total_protein_g: 31.5,
    total_fat_g: 23.1,
    total_fiber_g: 0,
    total_kcal: 627,
    items: [
      {
        id: "item-1",
        meal_id: "meal-1",
        name: "Тако с курицей и овощами ×2",
        brand: null,
        grams: 350,
        serving_text: "2 упаковки по 175 г",
        carbs_g: 70.3,
        protein_g: 31.5,
        fat_g: 23.1,
        fiber_g: 0,
        kcal: 627,
        confidence: null,
        confidence_reason: null,
        source_kind: "manual",
        calculation_method: "manual",
        assumptions: [],
        evidence: { quantity: 2, net_weight_per_unit_g: 175 },
        warnings: [],
        pattern_id: null,
        product_id: null,
        photo_id: null,
        position: 0,
        nutrients: [],
        created_at: "2026-05-01T10:00:00.000Z",
        updated_at: "2026-05-01T10:00:00.000Z",
      },
    ],
  });
  const item = meal.items?.[0];
  expect(item).toBeDefined();

  const payload = favoriteProductPayload(meal, item!, mealQuantityInfo(meal));

  expect(payload.name).toBe("Тако с курицей и овощами");
  expect(payload.default_grams).toBe(175);
  expect(payload.carbs_per_serving).toBe(35.2);
  expect(payload.protein_per_serving).toBe(15.8);
  expect(payload.fat_per_serving).toBe(11.6);
  expect(payload.kcal_per_serving).toBe(314);
  expect(payload.carbs_per_100g).toBe(20.1);
});
