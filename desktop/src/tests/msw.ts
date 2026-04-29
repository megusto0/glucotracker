import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

const now = "2026-04-28T10:00:00.000Z";

const mealResponse = (overrides: Record<string, unknown> = {}) => ({
  id: "meal-1",
  eaten_at: now,
  title: "Test meal",
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
  created_at: now,
  updated_at: now,
  items: [],
  photos: [],
  ...overrides,
});

export const server = setupServer(
  http.get("http://api.test/health", () =>
    HttpResponse.json({ status: "ok", version: "0.1.0", db: "ok" }),
  ),
  http.get("http://api.test/openapi.json", () =>
    HttpResponse.json({ openapi: "3.1.0", info: { version: "0.1.0" } }),
  ),
  http.get("http://api.test/nightscout/status", () =>
    HttpResponse.json({ configured: false, status: null }),
  ),
  http.get("http://api.test/settings/nightscout", () =>
    HttpResponse.json({
      enabled: false,
      configured: false,
      connected: false,
      url: null,
      secret_is_set: false,
      last_status_check_at: null,
      last_error: null,
      sync_glucose: true,
      show_glucose_in_journal: true,
      import_insulin_events: true,
      allow_meal_send: true,
      confirm_before_send: true,
      autosend_meals: false,
    }),
  ),
  http.put("http://api.test/settings/nightscout", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      enabled: Boolean(body.nightscout_enabled),
      configured: Boolean(body.nightscout_url && body.nightscout_api_secret),
      connected: false,
      url: body.nightscout_url ?? null,
      secret_is_set: Boolean(body.nightscout_api_secret),
      last_status_check_at: null,
      last_error: null,
      sync_glucose: body.sync_glucose ?? true,
      show_glucose_in_journal: body.show_glucose_in_journal ?? true,
      import_insulin_events: body.import_insulin_events ?? true,
      allow_meal_send: body.allow_meal_send ?? true,
      confirm_before_send: body.confirm_before_send ?? true,
      autosend_meals: false,
    });
  }),
  http.post("http://api.test/settings/nightscout/test", () =>
    HttpResponse.json({
      ok: false,
      status: null,
      server_name: null,
      version: null,
      error: "Nightscout не подключён",
    }),
  ),
  http.get("http://api.test/nightscout/day_status", () =>
    HttpResponse.json({
      connected: false,
      configured: false,
      accepted_meals_count: 0,
      unsynced_meals_count: 0,
      synced_meals_count: 0,
      failed_meals_count: 0,
      last_sync_at: null,
    }),
  ),
  http.post("http://api.test/nightscout/sync/today", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      date: body.date ?? "2026-04-28",
      total_candidates: 0,
      sent_count: 0,
      skipped_count: 0,
      failed_count: 0,
      results: [],
    });
  }),
  http.get("http://api.test/nightscout/events", () =>
    HttpResponse.json({ glucose: [], insulin: [] }),
  ),
  http.post("http://api.test/nightscout/import", () =>
    HttpResponse.json({
      from_datetime: "2026-04-28T00:00:00",
      to_datetime: "2026-04-28T23:59:59",
      glucose_count: 0,
      insulin_count: 0,
    }),
  ),
  http.get("http://api.test/timeline", () =>
    HttpResponse.json({
      from_datetime: "2026-04-28T00:00:00",
      to_datetime: "2026-04-28T23:59:59",
      episodes: [],
      ungrouped_insulin: [],
    }),
  ),
  http.get("http://api.test/reports/endocrinologist", () =>
    HttpResponse.json({
      app_name: "glucotracker",
      title: "Отчёт для эндокринолога",
      period_label: "Период: 28 апреля 2026",
      generated_label: "Сгенерировано: 29 апреля 2026",
      chips: [
        { label: "1 дней" },
        { label: "0/1 дней с едой" },
        { label: "CGM coverage —" },
        { label: "0 пищевых эпизода" },
      ],
      warning: "Данных мало: 0 дней с едой из 1 выбранных",
      notes: ["CGM нет за период", "Инсулин не найден"],
      kpis: [
        {
          label: "ИНСУЛИН ЗАВТРАК",
          value: "—",
          unit: "",
          caption: "медиана за период",
        },
        {
          label: "ИНСУЛИН ОБЕД",
          value: "—",
          unit: "",
          caption: "медиана за период",
        },
        {
          label: "ИНСУЛИН УЖИН",
          value: "—",
          unit: "",
          caption: "медиана за период",
        },
        {
          label: "ИНСУЛИН ЗА ДЕНЬ",
          value: "—",
          unit: "",
          caption: "медиана за период",
        },
        {
          label: "САХАР ДО ЕДЫ",
          value: "—",
          unit: "",
          caption: "медиана за период",
        },
        {
          label: "САХАР ПОСЛЕ ЕДЫ",
          value: "—",
          unit: "",
          caption: "медиана за период",
        },
        {
          label: "НАБЛЮДАЕМЫЙ УК",
          value: "—",
          unit: "",
          caption: "по всем эпизодам",
        },
        {
          label: "TIR 3.9-10.0",
          value: "—",
          unit: "",
          caption: "CGM нет",
        },
      ],
      meal_profile_rows: [],
      daily_rows: [],
      shown_daily_rows: [],
      daily_median_row: {
        date: "median",
        date_label: "Медиана",
        carbs: "—",
        insulin: "—",
        tir: "—",
        hypo: "0",
        breakfast: "—",
        lunch: "—",
        dinner: "—",
        flagged: false,
      },
      daily_rows_note: null,
      bottom_metrics: [],
      footer:
        "Инсулин получен из Nightscout (только чтение). Отчёт информационный и не является медицинской рекомендацией.",
    }),
  ),
  http.get("http://api.test/meals", () =>
    HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
  ),
  http.post("http://api.test/meals", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(mealResponse(body), { status: 201 });
  }),
  http.get("http://api.test/meals/:mealId", () =>
    HttpResponse.json(mealResponse()),
  ),
  http.patch("http://api.test/meals/:mealId", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(mealResponse(body));
  }),
  http.delete("http://api.test/meals/:mealId", () =>
    HttpResponse.json({ deleted: true }),
  ),
  http.put("http://api.test/meals/:mealId/items", async ({ request }) => {
    const items = await request.json();
    return HttpResponse.json(mealResponse({ items }));
  }),
  http.patch("http://api.test/meal_items/:itemId", async ({ params, request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      id: params.itemId,
      meal_id: "meal-1",
      name: "Coffee",
      brand: null,
      grams: null,
      serving_text: null,
      carbs_g: 0,
      protein_g: 0,
      fat_g: 0,
      fiber_g: 0,
      kcal: 0,
      confidence: null,
      confidence_reason: null,
      source_kind: "manual",
      calculation_method: null,
      assumptions: [],
      evidence: {},
      warnings: [],
      nutrients: [],
      pattern_id: null,
      product_id: null,
      photo_id: null,
      position: 0,
      created_at: now,
      updated_at: now,
      image_url: null,
      image_cache_path: null,
      source_image_url: null,
      ...body,
    });
  }),
  http.get("http://api.test/autocomplete", () =>
    HttpResponse.json([
      {
        kind: "pattern",
        id: "pattern-1",
        token: "bk:whopper",
        display_name: "Whopper",
        subtitle: "bk:whopper",
        carbs_g: 51,
        protein_g: 28,
        fat_g: 35,
        kcal: 635,
        image_url: "https://example.test/whopper.png",
        usage_count: 7,
        matched_alias: "whopper",
      },
    ]),
  ),
  http.get("http://api.test/database/items", ({ request }) => {
    const query = new URL(request.url).searchParams.get("q") ?? "";
    const allItems = [
      {
        id: "pattern-1",
        kind: "restaurant",
        prefix: "bk",
        key: "whopper",
        token: "bk:whopper",
        display_name: "Whopper",
        subtitle: "bk:whopper",
        image_url: "https://example.test/whopper.png",
        image_cache_path: null,
        carbs_g: 51,
        protein_g: 28,
        fat_g: 35,
        fiber_g: 3,
        kcal: 635,
        default_grams: 270,
        usage_count: 7,
        last_used_at: "2026-04-28T10:00:00.000Z",
        source_name: "Burger King",
        source_url: "https://origin.bk.com/pdfs/nutrition.pdf",
        source_confidence: null,
        is_verified: false,
        aliases: ["воппер", "whopper"],
        nutrients_json: { sodium_mg: { amount: 980, unit: "mg" } },
        quality_warnings: [],
      },
      {
        id: "product-1",
        kind: "product",
        prefix: null,
        key: null,
        token: "4601234567890",
        display_name: "Protein Drink",
        subtitle: "Example · 4601234567890",
        image_url: "https://example.test/drink.png",
        image_cache_path: null,
        carbs_g: 12,
        protein_g: 25,
        fat_g: 2,
        fiber_g: 1,
        kcal: 166,
        default_grams: 330,
        usage_count: 2,
        last_used_at: null,
        source_name: "Example",
        source_url: null,
        source_confidence: null,
        is_verified: false,
        aliases: ["drink"],
        nutrients_json: {},
        quality_warnings: ["нужно проверить"],
      },
    ];
    const items = query
      ? allItems.filter((item) =>
          [item.display_name, item.token, item.subtitle, ...item.aliases]
            .filter(Boolean)
            .some((value) => value.toLowerCase().includes(query.toLowerCase())),
        )
      : allItems;
    return HttpResponse.json({
      items,
      total: items.length,
      limit: 100,
      offset: 0,
    });
  }),
  http.post("http://api.test/meals/:mealId/photos", () =>
    HttpResponse.json(
      {
        id: "photo-1",
        meal_id: "meal-1",
        path: "2026/04/photo-1.jpg",
        original_filename: "photo.jpg",
        content_type: "image/jpeg",
        taken_at: null,
        scenario: "unknown",
        has_reference_object: false,
        reference_kind: "none",
        gemini_response_raw: null,
        created_at: now,
      },
      { status: 201 },
    ),
  ),
  http.get("http://api.test/photos/:photoId/file", () =>
    HttpResponse.text("image-bytes", {
      headers: { "Content-Type": "image/jpeg" },
    }),
  ),
  http.post("http://api.test/meals/:mealId/estimate_and_save_draft", () =>
    HttpResponse.json({
      meal_id: "meal-1",
      source_photos: [
        {
          id: "photo-1",
          url: "/photos/photo-1/file",
          thumbnail_url: "/photos/photo-1/file",
        },
      ],
      suggested_items: [
        {
          name: "Chicken and potatoes",
          carbs_g: 34,
          protein_g: 28,
          fat_g: 12,
          fiber_g: 4,
          kcal: 360,
          confidence: 0.55,
          confidence_reason: "Clear plate, but portion size is uncertain.",
          source_kind: "photo_estimate",
          calculation_method: "visual_estimate_gemini_mid",
          assumptions: ["Portion estimated from plate size."],
          evidence: { scenario: "PLATED" },
          warnings: [],
          position: 0,
        },
      ],
      suggested_totals: {
        total_carbs_g: 34,
        total_protein_g: 28,
        total_fat_g: 12,
        total_fiber_g: 4,
        total_kcal: 360,
      },
      calculation_breakdowns: [
        {
          position: 0,
          name: "Chicken and potatoes",
          count_detected: null,
          net_weight_per_unit_g: null,
          total_weight_g: 300,
          nutrition_per_100g: null,
          calculated_per_unit: null,
          calculated_total: {
            carbs_g: 34,
            protein_g: 28,
            fat_g: 12,
            fiber_g: 4,
            kcal: 360,
          },
          calculation_steps: [],
          evidence: ["Visible plate with chicken and potatoes."],
          assumptions: ["Portion estimated from plate size."],
        },
      ],
      gemini_notes: "Draft generated.",
      image_quality_warnings: [],
      reference_detected: "plate",
      ai_run_id: "ai-run-1",
    }),
  ),
  http.post("http://api.test/meals/:mealId/accept", async ({ request }) => {
    const body = (await request.json()) as { items?: unknown[] };
    return HttpResponse.json(
      mealResponse({
        status: "accepted",
        source: "photo",
        items: body.items ?? [],
      }),
    );
  }),
  http.post("http://api.test/meals/:mealId/discard", () =>
    HttpResponse.json(mealResponse({ status: "discarded" })),
  ),
  http.get("http://api.test/dashboard/today", () =>
    HttpResponse.json({
      date: "2026-04-28",
      kcal: 0,
      carbs_g: 0,
      protein_g: 0,
      fat_g: 0,
      fiber_g: 0,
      meal_count: 0,
      last_meal_at: null,
      hours_since_last_meal: null,
      week_avg_carbs: 0,
      week_avg_kcal: 0,
      prev_week_avg_carbs: 0,
      prev_week_avg_kcal: 0,
    }),
  ),
  http.get("http://api.test/dashboard/range", () =>
    HttpResponse.json({
      days: [],
      summary: {
        avg_kcal: 0,
        avg_carbs_g: 0,
        avg_protein_g: 0,
        avg_fat_g: 0,
        avg_fiber_g: 0,
        total_kcal: 0,
        total_carbs_g: 0,
        total_protein_g: 0,
        total_fat_g: 0,
        total_fiber_g: 0,
        total_meals: 0,
      },
    }),
  ),
  http.get("http://api.test/dashboard/heatmap", () =>
    HttpResponse.json({ cells: [] }),
  ),
  http.get("http://api.test/dashboard/top_patterns", () =>
    HttpResponse.json([]),
  ),
  http.get("http://api.test/dashboard/source_breakdown", () =>
    HttpResponse.json({ days: 7, items: [] }),
  ),
  http.get("http://api.test/dashboard/data_quality", () =>
    HttpResponse.json({
      exact_label_count: 0,
      assumed_label_count: 0,
      restaurant_db_count: 0,
      product_db_count: 0,
      pattern_count: 0,
      visual_estimate_count: 0,
      manual_count: 0,
      low_confidence_count: 0,
      total_item_count: 0,
      low_confidence_items: [],
    }),
  ),
  http.post("http://api.test/admin/recalculate", () =>
    HttpResponse.json({
      from_date: "2026-04-01",
      to_date: "2026-04-30",
      days_recalculated: 30,
    }),
  ),
);
