import { http, HttpResponse } from "msw";
import { apiClient } from "../api/client";
import { server } from "./msw";

test("API client attaches bearer token", async () => {
  let authorization: string | null = null;

  server.use(
    http.get("http://api.test/meals", ({ request }) => {
      authorization = request.headers.get("authorization");
      return HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 });
    }),
  );

  await apiClient.listMeals(
    { baseUrl: "http://api.test", token: "test-token" },
    { limit: 20 },
  );

  expect(authorization).toBe("Bearer test-token");
});

test("API client patches meal eaten_at", async () => {
  let method = "";
  let body: Record<string, unknown> | null = null;

  server.use(
    http.patch("http://api.test/meals/:mealId", async ({ request }) => {
      method = request.method;
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        id: "meal-1",
        eaten_at: body.eaten_at,
        title: "Meal",
        note: null,
        status: "accepted",
        source: "manual",
        total_carbs_g: 0,
        total_protein_g: 0,
        total_fat_g: 0,
        total_fiber_g: 0,
        total_kcal: 0,
        confidence: null,
        nightscout_synced_at: null,
        nightscout_id: null,
        created_at: "2026-04-28T10:00:00.000Z",
        updated_at: "2026-04-28T10:05:00.000Z",
        items: [],
        photos: [],
        thumbnail_url: null,
      });
    }),
  );

  await apiClient.updateMeal(
    { baseUrl: "http://api.test", token: "test-token" },
    "meal-1",
    { eaten_at: "2026-04-28T12:30:00.000Z" },
  );

  expect(method).toBe("PATCH");
  expect(body).toEqual({ eaten_at: "2026-04-28T12:30:00.000Z" });
});
