import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import App from "../App";
import { useSettingsStore } from "../features/settings/settingsStore";
import { server } from "./msw";

const currentDateHeading = new RegExp(
  new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  })
    .format(new Date())
    .replace(" г.", ""),
  "i",
);

const formatDayHeading = (date: Date) =>
  new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  })
    .format(date)
    .replace(" Рі.", "");

const startOfLocalDay = (date: Date) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate());

const addDays = (date: Date, days: number) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);

const toLocalDateTimeString = (date: Date) => {
  const pad = (value: number) => value.toString().padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate(),
  )}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(
    date.getSeconds(),
  )}`;
};

const configureApi = () => {
  useSettingsStore.setState({
    baseUrl: "http://api.test",
    token: "dev-token",
  });
};

const commandInput = () =>
  screen.getByRole("textbox", { name: "Командный ввод" });

const feedRoute = () => {
  window.history.pushState({}, "", "/feed");
};

const statsRoute = () => {
  window.history.pushState({}, "", "/stats");
};

const glucoseRoute = () => {
  window.history.pushState({}, "", "/glucose");
};

const settingsRoute = () => {
  window.history.pushState({}, "", "/settings");
};

const databaseRoute = () => {
  window.history.pushState({}, "", "/database");
};

const mealFixture = (overrides: Record<string, unknown> = {}) => ({
  id: "meal-1",
  eaten_at: "2026-04-28T10:00:00.000Z",
  title: "Coffee",
  note: null,
  status: "accepted",
  source: "manual",
  total_carbs_g: 22,
  total_protein_g: 12,
  total_fat_g: 8,
  total_fiber_g: 1,
  total_kcal: 310,
  confidence: null,
  nightscout_synced_at: null,
  nightscout_id: null,
  thumbnail_url: null,
  created_at: "2026-04-28T10:00:00.000Z",
  updated_at: "2026-04-28T10:00:00.000Z",
  items: [
    {
      id: "item-1",
      meal_id: "meal-1",
      name: "Coffee",
      brand: null,
      grams: null,
      serving_text: null,
      carbs_g: 22,
      protein_g: 12,
      fat_g: 8,
      fiber_g: 1,
      kcal: 310,
      confidence: null,
      confidence_reason: null,
      source_kind: "manual",
      calculation_method: "manual",
      assumptions: [],
      evidence: {},
      warnings: [],
      pattern_id: null,
      product_id: null,
      photo_id: null,
      image_url: null,
      image_cache_path: null,
      source_image_url: null,
      position: 0,
      created_at: "2026-04-28T10:00:00.000Z",
      updated_at: "2026-04-28T10:00:00.000Z",
    },
  ],
  photos: [],
  ...overrides,
});

const useDashboardFixture = () => {
  server.use(
    http.get("http://api.test/dashboard/today", () =>
      HttpResponse.json({
        date: "2026-04-28",
        carbs_g: 186,
        kcal: 2140,
        protein_g: 98,
        fat_g: 74,
        fiber_g: 18,
        meal_count: 5,
        last_meal_at: "2026-04-28T18:00:00.000Z",
        hours_since_last_meal: 4.2,
        week_avg_carbs: 152,
        week_avg_kcal: 1880,
        prev_week_avg_carbs: 140,
        prev_week_avg_kcal: 1760,
      }),
    ),
    http.get("http://api.test/dashboard/range", () =>
      HttpResponse.json({
        days: [
          {
            date: "2026-04-26",
            kcal: 1600,
            carbs_g: 120,
            protein_g: 80,
            fat_g: 50,
            fiber_g: 12,
            meal_count: 3,
          },
          {
            date: "2026-04-27",
            kcal: 1900,
            carbs_g: 150,
            protein_g: 90,
            fat_g: 60,
            fiber_g: 16,
            meal_count: 4,
          },
          {
            date: "2026-04-28",
            kcal: 2140,
            carbs_g: 186,
            protein_g: 98,
            fat_g: 74,
            fiber_g: 18,
            meal_count: 5,
          },
        ],
        summary: {
          avg_kcal: 1880,
          avg_carbs_g: 152,
          avg_protein_g: 89,
          avg_fat_g: 61,
          avg_fiber_g: 15,
          total_kcal: 5640,
          total_carbs_g: 456,
          total_protein_g: 268,
          total_fat_g: 184,
          total_fiber_g: 46,
          total_meals: 12,
        },
      }),
    ),
    http.get("http://api.test/dashboard/heatmap", () =>
      HttpResponse.json({
        cells: [
          { day_of_week: 0, hour: 8, avg_carbs_g: 22, meal_count: 2 },
          { day_of_week: 1, hour: 13, avg_carbs_g: 98, meal_count: 3 },
          { day_of_week: 4, hour: 19, avg_carbs_g: 66, meal_count: 1 },
        ],
      }),
    ),
    http.get("http://api.test/dashboard/top_patterns", () =>
      HttpResponse.json([
        {
          pattern_id: "11111111-1111-1111-1111-111111111111",
          token: "bk:whopper",
          display_name: "BK: Whopper",
          count: 3,
        },
      ]),
    ),
    http.get("http://api.test/dashboard/source_breakdown", () =>
      HttpResponse.json({
        days: 7,
        items: [
          { source_kind: "pattern", count: 5 },
          { source_kind: "manual", count: 3 },
          { source_kind: "photo_estimate", count: 2 },
        ],
      }),
    ),
    http.get("http://api.test/dashboard/data_quality", () =>
      HttpResponse.json({
        exact_label_count: 2,
        assumed_label_count: 1,
        restaurant_db_count: 3,
        product_db_count: 2,
        pattern_count: 5,
        visual_estimate_count: 2,
        manual_count: 3,
        low_confidence_count: 1,
        total_item_count: 18,
        low_confidence_items: [
          {
            meal_id: "meal-low",
            item_id: "item-low",
            name: "Unclear plated meal",
            confidence: 0.42,
            reason: "No reference object.",
          },
        ],
      }),
    ),
  );
};

test("app renders", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: currentDateHeading })).toBeInTheDocument();
});

test("journal previous day button loads yesterday meals", async () => {
  configureApi();
  const user = userEvent.setup();
  const today = startOfLocalDay(new Date());
  const yesterday = addDays(today, -1);
  const todayFrom = toLocalDateTimeString(today);
  const yesterdayFrom = toLocalDateTimeString(yesterday);

  server.use(
    http.get("http://api.test/meals", ({ request }) => {
      const from = new URL(request.url).searchParams.get("from");
      const items =
        from === yesterdayFrom
          ? [
              mealFixture({
                id: "meal-yesterday",
                eaten_at: new Date(
                  yesterday.getFullYear(),
                  yesterday.getMonth(),
                  yesterday.getDate(),
                  12,
                  30,
                  0,
                ).toISOString(),
                title: "Yesterday meal",
              }),
            ]
          : from === todayFrom
            ? []
            : [];

      return HttpResponse.json({
        items,
        total: items.length,
        limit: 100,
        offset: 0,
      });
    }),
  );

  render(<App />);

  expect(await screen.findByRole("button", { name: "Предыдущий день" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Предыдущий день" }));

  expect(await screen.findByText("Yesterday meal")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Вернуться к сегодня" }),
  ).toHaveTextContent(formatDayHeading(yesterday));
  expect(
    screen.getByRole("heading", {
      name: new RegExp(formatDayHeading(yesterday), "i"),
    }),
  ).toBeInTheDocument();
});

test.each([
  { path: "/", heading: currentDateHeading },
  { path: "/feed", heading: /^История$/i },
  { path: "/stats", heading: /^Статистика$/i },
  { path: "/database", heading: /^База$/i },
  { path: "/settings", heading: /^Интеграция: Nightscout$/i },
])("smoke renders $path route", ({ path, heading }) => {
  window.history.pushState({}, "", path);

  render(<App />);

  expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
});

test("navigation between routes works", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("link", { name: "Статистика" }));
  expect(
    screen.getByRole("heading", { name: "Статистика" }),
  ).toBeInTheDocument();

  await user.click(screen.getByRole("link", { name: "История" }));
  expect(screen.getByRole("heading", { name: "История" })).toBeInTheDocument();

  await user.click(screen.getByRole("link", { name: "База" }));
  expect(screen.getByRole("heading", { name: "База" })).toBeInTheDocument();
});

test("settings persist after reload", async () => {
  const user = userEvent.setup();
  const { unmount } = render(<App />);

  await user.click(screen.getByRole("link", { name: "Настройки" }));
  await user.clear(screen.getByLabelText("Адрес backend"));
  await user.type(screen.getByLabelText("Адрес backend"), "http://api.test");
  await user.type(screen.getByLabelText("Bearer-токен"), "dev-token");
  unmount();

  render(<App />);
  await user.click(screen.getByRole("link", { name: "Настройки" }));

  expect(screen.getByLabelText("Адрес backend")).toHaveValue("http://api.test");
  expect(screen.getByLabelText("Bearer-токен")).toHaveValue("dev-token");
});

test("test connection calls health and OpenAPI", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("link", { name: "Настройки" }));
  await user.clear(screen.getByLabelText("Адрес backend"));
  await user.type(screen.getByLabelText("Адрес backend"), "http://api.test");
  await user.click(screen.getByRole("button", { name: "Проверить backend" }));

  await waitFor(() => {
    expect(screen.getByText("ok / v0.1.0")).toBeInTheDocument();
  });
  expect(screen.getByText("доступен")).toBeInTheDocument();
});

test("settings Nightscout block handles not configured", async () => {
  configureApi();
  settingsRoute();

  render(<App />);
  expect(await screen.findByText("Синхронизация")).toBeInTheDocument();
  expect(await screen.findAllByText("не настроено")).not.toHaveLength(0);
});

test("white background token is applied", () => {
  render(<App />);

  expect(
    getComputedStyle(document.documentElement).getPropertyValue("--bg").trim(),
  ).toBe("#f7f5ef");
});

test("typing prefix query triggers debounced autocomplete", async () => {
  configureApi();
  const user = userEvent.setup();
  let autocompleteCalls = 0;
  let latestQuery = "";

  server.use(
    http.get("http://api.test/autocomplete", ({ request }) => {
      autocompleteCalls += 1;
      latestQuery = new URL(request.url).searchParams.get("q") ?? "";
      return HttpResponse.json([]);
    }),
  );

  render(<App />);
  await user.type(commandInput(), "bk:");

  await waitFor(() => expect(autocompleteCalls).toBeGreaterThan(0));
  expect(latestQuery).toBe("bk:");
});

test("typing plain text triggers autocomplete after two characters", async () => {
  configureApi();
  const user = userEvent.setup();
  let latestQuery = "";

  server.use(
    http.get("http://api.test/autocomplete", ({ request }) => {
      latestQuery = new URL(request.url).searchParams.get("q") ?? "";
      return HttpResponse.json([]);
    }),
  );

  render(<App />);
  await user.type(commandInput(), "сырок");

  await waitFor(() => expect(latestQuery).toBe("сырок"));
});

test("autocomplete rounds nutrition numbers without overflowing decimals", async () => {
  configureApi();
  const user = userEvent.setup();

  server.use(
    http.get("http://api.test/autocomplete", () =>
      HttpResponse.json([
        {
          kind: "product",
          id: "product-rounded",
          token: "Сырок глазированный",
          display_name: "Сырок глазированный с очень длинным названием",
          subtitle: "Эффер · 1 шт",
          carbs_g: 13.200000000000001,
          protein_g: 2.6666666667,
          fat_g: 9.999999999,
          kcal: 165.20000000000003,
          image_url: null,
          usage_count: 0,
          matched_alias: "сырок",
        },
      ]),
    ),
  );

  render(<App />);
  await user.type(commandInput(), "сырок");

  expect(await screen.findByText("13.2У")).toBeInTheDocument();
  expect(screen.getByText("2.7Б")).toBeInTheDocument();
  expect(screen.getByText("10Ж")).toBeInTheDocument();
  expect(screen.getByText("165 ккал")).toBeInTheDocument();
});

test("selecting autocomplete suggestion creates a chip", async () => {
  configureApi();
  const user = userEvent.setup();

  render(<App />);
  await user.type(commandInput(), "bk:wh");
  await user.click(await screen.findByRole("button", { name: /Whopper/i }));

  expect(
    screen.getByRole("button", { name: /bk:whopper/i }),
  ).toBeInTheDocument();
});

test("enter with chip creates pattern meal", async () => {
  configureApi();
  const user = userEvent.setup();
  let createdBody: Record<string, unknown> | null = null;

  server.use(
    http.post("http://api.test/meals", async ({ request }) => {
      createdBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        {
          id: "meal-1",
          eaten_at: "2026-04-28T10:00:00Z",
          created_at: "2026-04-28T10:00:00Z",
          updated_at: "2026-04-28T10:00:00Z",
          title: createdBody.title,
          note: null,
          status: "accepted",
          source: createdBody.source,
          total_carbs_g: 51,
          total_protein_g: 28,
          total_fat_g: 35,
          total_fiber_g: 0,
          total_kcal: 635,
          confidence: null,
          nightscout_id: null,
          nightscout_synced_at: null,
          items: [],
          photos: [],
        },
        { status: 201 },
      );
    }),
  );

  render(<App />);
  await user.type(commandInput(), "bk:wh");
  await user.click(await screen.findByRole("button", { name: /Whopper/i }));
  await user.type(commandInput(), "{Enter}");

  await waitFor(() => expect(createdBody?.source).toBe("pattern"));
  const createdItems = (
    createdBody as {
      items?: Array<Record<string, unknown>>;
    } | null
  )?.items;
  expect(createdItems?.[0]).toMatchObject({
    pattern_id: "pattern-1",
    source_kind: "pattern",
  });
});

test("enter plain text creates manual meal", async () => {
  configureApi();
  const user = userEvent.setup();
  let createdBody: Record<string, unknown> | null = null;

  server.use(
    http.post("http://api.test/meals", async ({ request }) => {
      createdBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        { ...createdBody, id: "meal-1" },
        { status: 201 },
      );
    }),
  );

  render(<App />);
  await user.type(commandInput(), "eggs{Enter}");

  await waitFor(() => expect(createdBody?.source).toBe("manual"));
  expect((createdBody as Record<string, unknown> | null)?.eaten_at).toEqual(
    expect.stringMatching(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/),
  );
  const createdItems = (
    createdBody as {
      items?: Array<Record<string, unknown>>;
    } | null
  )?.items;
  expect(createdItems?.[0]).toMatchObject({
    name: "eggs",
    carbs_g: 0,
    kcal: 0,
    source_kind: "manual",
  });
});

test("saved product autocomplete logs product without Gemini and supports quantity", async () => {
  configureApi();
  const user = userEvent.setup();
  let createdBody: Record<string, unknown> | null = null;
  let estimateCalls = 0;

  server.use(
    http.get("http://api.test/autocomplete", ({ request }) => {
      const query = new URL(request.url).searchParams.get("q") ?? "";
      if (query.includes("сырок")) {
        return HttpResponse.json([
          {
            kind: "product",
            id: "product-syrok",
            token: "Сырок глазированный",
            display_name: "Сырок глазированный",
            subtitle: "40 г · продукт",
            carbs_g: 27,
            protein_g: 7,
            fat_g: 17,
            kcal: 293,
            image_url: "https://example.test/syrok.png",
            usage_count: 0,
            matched_alias: "сырок",
          },
        ]);
      }
      return HttpResponse.json([]);
    }),
    http.post("http://api.test/meals", async ({ request }) => {
      createdBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        { ...createdBody, id: "meal-product-1" },
        { status: 201 },
      );
    }),
    http.post("http://api.test/meals/:mealId/estimate_and_save_draft", () => {
      estimateCalls += 1;
      return HttpResponse.json({});
    }),
  );

  render(<App />);
  await user.type(commandInput(), "сырок");
  await user.click(
    await screen.findByRole("button", { name: /Сырок глазированный/i }),
  );
  await user.clear(screen.getByLabelText("Количество Сырок глазированный"));
  await user.type(screen.getByLabelText("Количество Сырок глазированный"), "2");
  await user.type(commandInput(), "{Enter}");

  await waitFor(() => expect(createdBody?.source).toBe("mixed"));
  const createdItems = (
    createdBody as {
      items?: Array<Record<string, unknown>>;
    } | null
  )?.items;
  expect(createdItems?.[0]).toMatchObject({
    product_id: "product-syrok",
    source_kind: "product_db",
    evidence: expect.objectContaining({ quantity: 2 }),
  });
  expect(estimateCalls).toBe(0);
});

test("selected journal meal can be deleted", async () => {
  configureApi();
  const user = userEvent.setup();
  let deletedMealId: string | null = null;

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: deletedMealId ? [] : [mealFixture()],
        total: deletedMealId ? 0 : 1,
        limit: 100,
        offset: 0,
      }),
    ),
    http.delete("http://api.test/meals/:mealId", ({ params }) => {
      deletedMealId = String(params.mealId);
      return HttpResponse.json({ deleted: true });
    }),
  );

  render(<App />);
  await user.click(await screen.findByText("Coffee"));
  await user.click(screen.getByRole("button", { name: "Удалить" }));

  await waitFor(() => expect(deletedMealId).toBe("meal-1"));
  await waitFor(() =>
    expect(screen.queryByText("Coffee")).not.toBeInTheDocument(),
  );
});

test("selected journal meal date and time can be edited", async () => {
  configureApi();
  const user = userEvent.setup();
  let patchBody: Record<string, unknown> | null = null;
  const originalMeal = mealFixture({
    eaten_at: "2026-04-28T10:00:00.000Z",
    title: "Coffee",
  });

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [originalMeal],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
    http.patch("http://api.test/meals/:mealId", async ({ request }) => {
      patchBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ ...originalMeal, ...patchBody });
    }),
  );

  render(<App />);
  await user.click(await screen.findByText("Coffee"));
  fireEvent.change(screen.getByLabelText("Дата и время записи"), {
    target: { value: "2026-05-01T13:45" },
  });
  await user.click(screen.getByRole("button", { name: "Сохранить дату" }));

  await waitFor(() =>
    expect(patchBody).toEqual({ eaten_at: "2026-05-01T13:45:00" }),
  );
});

test("selected journal meal name can be edited", async () => {
  configureApi();
  const user = userEvent.setup();
  let currentMeal = mealFixture({
    eaten_at: "2026-04-28T10:00:00.000Z",
    title: "Бисквит-сэндвич Royal Cake",
    items: [
      {
        ...(mealFixture().items as Array<Record<string, unknown>>)[0],
        name: "Бисквит-сэндвич Royal Cake",
      },
    ],
  });
  let mealPatchBody: Record<string, unknown> | null = null;
  let itemPatchBody: Record<string, unknown> | null = null;

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [currentMeal],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
    http.patch("http://api.test/meals/:mealId", async ({ request }) => {
      mealPatchBody = (await request.json()) as Record<string, unknown>;
      currentMeal = { ...currentMeal, ...mealPatchBody };
      return HttpResponse.json(currentMeal);
    }),
    http.patch("http://api.test/meal_items/:itemId", async ({ request }) => {
      const patch = (await request.json()) as Partial<
        (typeof currentMeal.items)[number]
      >;
      itemPatchBody = patch;
      currentMeal = {
        ...currentMeal,
        items: currentMeal.items.map((item) =>
          item.id === "item-1" ? { ...item, ...patch } : item,
        ),
      };
      return HttpResponse.json({
        ...currentMeal.items[0],
        ...patch,
      });
    }),
  );

  render(<App />);
  await user.click(await screen.findByText("Бисквит-сэндвич Royal Cake"));
  await user.clear(screen.getByLabelText("Название записи"));
  await user.type(screen.getByLabelText("Название записи"), "Протеиновый брауни Shagi");
  await user.click(screen.getByRole("button", { name: "Сохранить название" }));

  await waitFor(() =>
    expect(mealPatchBody).toEqual({ title: "Протеиновый брауни Shagi" }),
  );
  await waitFor(() =>
    expect(itemPatchBody).toEqual({ name: "Протеиновый брауни Shagi" }),
  );
});

test("selected journal product meal name updates the saved database product", async () => {
  configureApi();
  const user = userEvent.setup();
  let currentMeal = mealFixture({
    eaten_at: "2026-04-28T10:00:00.000Z",
    title: "Wrong product name",
    source: "photo",
    items: [
      {
        ...(mealFixture().items as Array<Record<string, unknown>>)[0],
        name: "Wrong product name",
        source_kind: "product_db",
        product_id: "product-rename-1",
      },
    ],
  });
  let productPatchBody: Record<string, unknown> | null = null;

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [currentMeal],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
    http.patch("http://api.test/meals/:mealId", async ({ request }) => {
      const patch = (await request.json()) as Record<string, unknown>;
      currentMeal = { ...currentMeal, ...patch };
      return HttpResponse.json(currentMeal);
    }),
    http.patch("http://api.test/meal_items/:itemId", async ({ request }) => {
      const patch = (await request.json()) as Partial<
        (typeof currentMeal.items)[number]
      >;
      currentMeal = {
        ...currentMeal,
        items: currentMeal.items.map((item) =>
          item.id === "item-1" ? { ...item, ...patch } : item,
        ),
      };
      return HttpResponse.json({
        ...currentMeal.items[0],
        ...patch,
      });
    }),
    http.patch("http://api.test/products/:productId", async ({ params, request }) => {
      productPatchBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        id: params.productId,
        name: productPatchBody.name,
        barcode: null,
        brand: "Shagi",
        default_grams: 40,
        default_serving_text: "1 шт",
        carbs_per_100g: null,
        protein_per_100g: null,
        fat_per_100g: null,
        fiber_per_100g: null,
        kcal_per_100g: null,
        carbs_per_serving: 27,
        protein_per_serving: 7,
        fat_per_serving: 17,
        fiber_per_serving: 0,
        kcal_per_serving: 293,
        source_kind: "label_calc",
        source_url: null,
        image_url: "/photos/product-rename-photo/file",
        nutrients_json: {},
        usage_count: 0,
        last_used_at: null,
        aliases: [],
        created_at: "2026-04-28T10:00:00.000Z",
        updated_at: "2026-04-28T10:00:00.000Z",
      });
    }),
  );

  render(<App />);
  await user.click(await screen.findByText("Wrong product name"));
  const nameInput = screen.getByDisplayValue("Wrong product name");
  await user.clear(nameInput);
  await user.type(nameInput, "Protein brownie Shagi");
  const form = nameInput.closest("form");
  expect(form).not.toBeNull();
  fireEvent.submit(form as HTMLFormElement);

  await waitFor(() =>
    expect(productPatchBody).toEqual({ name: "Protein brownie Shagi" }),
  );
});

test("selected journal label meal without product_id links and updates database product", async () => {
  configureApi();
  const user = userEvent.setup();
  let currentMeal = mealFixture({
    eaten_at: "2026-04-28T10:00:00.000Z",
    title: "Old photo label name",
    source: "photo",
    items: [
      {
        ...(mealFixture().items as Array<Record<string, unknown>>)[0],
        name: "Old photo label name",
        source_kind: "label_calc",
        calculation_method: "label_visible_weight_backend_calc",
        product_id: null,
      },
    ],
  });
  let rememberCalled = false;
  let productPatchBody: Record<string, unknown> | null = null;

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [currentMeal],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
    http.patch("http://api.test/meals/:mealId", async ({ request }) => {
      const patch = (await request.json()) as Record<string, unknown>;
      currentMeal = { ...currentMeal, ...patch };
      return HttpResponse.json(currentMeal);
    }),
    http.patch("http://api.test/meal_items/:itemId", async ({ request }) => {
      const patch = (await request.json()) as Partial<
        (typeof currentMeal.items)[number]
      >;
      currentMeal = {
        ...currentMeal,
        items: currentMeal.items.map((item) =>
          item.id === "item-1" ? { ...item, ...patch } : item,
        ),
      };
      return HttpResponse.json({
        ...currentMeal.items[0],
        ...patch,
      });
    }),
    http.post("http://api.test/meal_items/:itemId/remember_product", () => {
      rememberCalled = true;
      return HttpResponse.json({
        id: "product-linked-from-photo",
        name: "Protein brownie Shagi",
        barcode: null,
        brand: "Shagi",
        default_grams: 40,
        default_serving_text: "1 шт",
        carbs_per_100g: null,
        protein_per_100g: null,
        fat_per_100g: null,
        fiber_per_100g: null,
        kcal_per_100g: null,
        carbs_per_serving: 22.1,
        protein_per_serving: 3,
        fat_per_serving: 2.45,
        fiber_per_serving: 1.1,
        kcal_per_serving: 124,
        source_kind: "label_calc",
        source_url: null,
        image_url: "/photos/photo-label/file",
        nutrients_json: {},
        usage_count: 0,
        last_used_at: null,
        aliases: [],
        created_at: "2026-04-28T10:00:00.000Z",
        updated_at: "2026-04-28T10:00:00.000Z",
      });
    }),
    http.patch("http://api.test/products/:productId", async ({ request }) => {
      productPatchBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        id: "product-linked-from-photo",
        name: productPatchBody.name,
        barcode: null,
        brand: "Shagi",
        default_grams: 40,
        default_serving_text: "1 шт",
        carbs_per_100g: null,
        protein_per_100g: null,
        fat_per_100g: null,
        fiber_per_100g: null,
        kcal_per_100g: null,
        carbs_per_serving: 22.1,
        protein_per_serving: 3,
        fat_per_serving: 2.45,
        fiber_per_serving: 1.1,
        kcal_per_serving: 124,
        source_kind: "label_calc",
        source_url: null,
        image_url: "/photos/photo-label/file",
        nutrients_json: {},
        usage_count: 0,
        last_used_at: null,
        aliases: [],
        created_at: "2026-04-28T10:00:00.000Z",
        updated_at: "2026-04-28T10:00:00.000Z",
      });
    }),
  );

  render(<App />);
  await user.click(await screen.findByText("Old photo label name"));
  const nameInput = screen.getByDisplayValue("Old photo label name");
  await user.clear(nameInput);
  await user.type(nameInput, "Protein brownie Shagi");
  const form = nameInput.closest("form");
  expect(form).not.toBeNull();
  fireEvent.submit(form as HTMLFormElement);

  await waitFor(() => expect(rememberCalled).toBe(true));
  await waitFor(() =>
    expect(productPatchBody).toEqual({ name: "Protein brownie Shagi" }),
  );
});

test("accepted label meal offers remember product action", async () => {
  configureApi();
  const user = userEvent.setup();
  let rememberBody: Record<string, unknown> | null = null;

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [
          mealFixture({
            id: "meal-label-1",
            title: "Сырок глазированный",
            source: "photo",
            items: [
              {
                ...(mealFixture().items as Array<Record<string, unknown>>)[0],
                id: "item-label-1",
                meal_id: "meal-label-1",
                name: "Сырок глазированный",
                brand: "Example",
                grams: 40,
                carbs_g: 27,
                protein_g: 7,
                fat_g: 17,
                kcal: 293,
                source_kind: "label_calc",
                calculation_method: "label_visible_weight_backend_calc",
                evidence: {
                  nutrition_per_100g: {
                    carbs_g: 67.5,
                    protein_g: 17.5,
                    fat_g: 42.5,
                    kcal: 732.5,
                  },
                },
              },
            ],
          }),
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
    http.post(
      "http://api.test/meal_items/:itemId/remember_product",
      async ({ request }) => {
        rememberBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: "product-syrok",
          barcode: null,
          brand: "Example",
          name: "Сырок глазированный",
          default_grams: 40,
          default_serving_text: "1 шт",
          carbs_per_100g: 67.5,
          protein_per_100g: 17.5,
          fat_per_100g: 42.5,
          fiber_per_100g: null,
          kcal_per_100g: 732.5,
          carbs_per_serving: 27,
          protein_per_serving: 7,
          fat_per_serving: 17,
          fiber_per_serving: 0,
          kcal_per_serving: 293,
          source_kind: "label_calc",
          source_url: null,
          image_url: null,
          nutrients_json: {},
          usage_count: 0,
          last_used_at: null,
          created_at: "2026-04-28T10:00:00.000Z",
          updated_at: "2026-04-28T10:00:00.000Z",
          aliases: ["сырок", "глазированный сырок"],
        });
      },
    ),
  );

  render(<App />);
  await user.click(await screen.findByText("Сырок глазированный"));
  expect(
    screen.getByText("Можно добавить в базу продуктов."),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Запомнить продукт" }));

  await waitFor(() =>
    expect((rememberBody?.aliases as string[]) ?? []).toContain("сырок"),
  );
});

test("pasting image shows thumbnail", () => {
  configureApi();
  const file = new File(["image"], "meal.jpg", { type: "image/jpeg" });

  render(<App />);
  fireEvent.paste(commandInput(), {
    clipboardData: {
      files: [file],
    },
  });

  expect(screen.getByRole("img", { name: "meal.jpg" })).toBeInTheDocument();
});

test("image picker adds thumbnail", async () => {
  configureApi();
  const user = userEvent.setup();
  const file = new File(["image"], "picked.png", { type: "image/png" });

  render(<App />);
  await user.upload(screen.getByLabelText("Выбрать фото"), file);

  expect(screen.getByRole("img", { name: "picked.png" })).toBeInTheDocument();
});

test("dragging image onto Today adds pending photo", () => {
  configureApi();
  const file = new File(["image"], "dragged.webp", { type: "image/webp" });

  render(<App />);
  fireEvent.drop(commandInput(), {
    dataTransfer: {
      files: [file],
      items: [
        {
          kind: "file",
          type: "image/webp",
          getAsFile: () => file,
        },
      ],
    },
  });

  expect(screen.getByRole("img", { name: "dragged.webp" })).toBeInTheDocument();
});

test("unsupported photo drop shows Russian error", () => {
  configureApi();
  const file = new File(["file"], "document.pdf", { type: "application/pdf" });

  render(<App />);
  fireEvent.drop(commandInput(), {
    dataTransfer: {
      files: [file],
      items: [
        {
          kind: "file",
          type: "application/pdf",
          getAsFile: () => file,
        },
      ],
    },
  });

  expect(
    screen.getByText("Этот формат фото пока не поддерживается"),
  ).toBeInTheDocument();
});

test("estimate flow calls create meal upload and estimate_and_save_draft", async () => {
  configureApi();
  const user = userEvent.setup();
  const file = new File(["image"], "meal.jpg", { type: "image/jpeg" });
  const calls: string[] = [];
  let estimateBody: { context_note?: unknown; model?: unknown } = {};

  server.use(
    http.post("http://api.test/meals", async ({ request }) => {
      calls.push("create");
      const body = await request.json();
      return HttpResponse.json(
        {
          ...(body as Record<string, unknown>),
          id: "meal-1",
          eaten_at: "2026-04-28T10:00:00Z",
          created_at: "2026-04-28T10:00:00Z",
          updated_at: "2026-04-28T10:00:00Z",
          total_carbs_g: 0,
          total_protein_g: 0,
          total_fat_g: 0,
          total_fiber_g: 0,
          total_kcal: 0,
          confidence: null,
          nightscout_id: null,
          nightscout_synced_at: null,
          items: [],
          photos: [],
        },
        { status: 201 },
      );
    }),
    http.post("http://api.test/meals/:mealId/photos", () => {
      calls.push("upload");
      return HttpResponse.json({ id: "photo-1" }, { status: 201 });
    }),
    http.post(
      "http://api.test/meals/:mealId/estimate_and_save_draft",
      async ({ request }) => {
        calls.push("estimate");
        estimateBody = (await request.json()) as {
          context_note?: unknown;
          model?: unknown;
        };
        return HttpResponse.json({
        meal_id: "meal-1",
        suggested_items: [
          {
            name: "Chicken and potatoes",
            carbs_g: 34,
            protein_g: 28,
            fat_g: 12,
            fiber_g: 4,
            kcal: 360,
            confidence: 0.55,
            confidence_reason: "Uncertain portion.",
            source_kind: "photo_estimate",
            calculation_method: "visual_estimate_gemini_mid",
            assumptions: [],
            evidence: {},
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
        gemini_notes: "",
        image_quality_warnings: [],
        reference_detected: "plate",
        ai_run_id: "ai-run-1",
        });
      },
    ),
  );

  render(<App />);
  fireEvent.paste(commandInput(), {
    clipboardData: {
      files: [file],
    },
  });
  await user.type(
    screen.getByLabelText("Контекст для фото"),
    "100 г варёного риса",
  );
  await user.selectOptions(screen.getByRole("combobox"), "gemini-2.5-flash");
  await user.click(screen.getByRole("button", { name: "Оценить" }));

  await screen.findByDisplayValue("Chicken and potatoes");
  expect(calls).toEqual(["create", "upload", "estimate"]);
  expect(estimateBody.model).toBe("gemini-2.5-flash");
  expect(estimateBody.context_note).toBe("100 г варёного риса");
});

test("estimate failure shows backend detail", async () => {
  configureApi();
  const user = userEvent.setup();

  server.use(
    http.post("http://api.test/meals/:mealId/estimate_and_save_draft", () =>
      HttpResponse.json(
        { detail: "GEMINI_API_KEY is not configured" },
        { status: 503 },
      ),
    ),
  );

  render(<App />);
  fireEvent.paste(commandInput(), {
    clipboardData: {
      files: [new File(["image"], "meal.jpg", { type: "image/jpeg" })],
    },
  });
  await user.click(screen.getByRole("button", { name: "Оценить" }));

  expect(
    await screen.findByText("GEMINI_API_KEY is not configured"),
  ).toBeInTheDocument();
});

test("estimate retry reuses the uploaded draft photos", async () => {
  configureApi();
  const user = userEvent.setup();
  const calls: string[] = [];
  let estimateCalls = 0;

  server.use(
    http.post("http://api.test/meals", async ({ request }) => {
      calls.push("create");
      const body = await request.json();
      return HttpResponse.json(
        {
          ...(body as Record<string, unknown>),
          id: "meal-1",
          eaten_at: "2026-04-28T10:00:00Z",
          created_at: "2026-04-28T10:00:00Z",
          updated_at: "2026-04-28T10:00:00Z",
          total_carbs_g: 0,
          total_protein_g: 0,
          total_fat_g: 0,
          total_fiber_g: 0,
          total_kcal: 0,
          confidence: null,
          nightscout_id: null,
          nightscout_synced_at: null,
          items: [],
          photos: [],
        },
        { status: 201 },
      );
    }),
    http.post("http://api.test/meals/:mealId/photos", () => {
      calls.push("upload");
      return HttpResponse.json({ id: "photo-1" }, { status: 201 });
    }),
    http.post("http://api.test/meals/:mealId/estimate_and_save_draft", () => {
      estimateCalls += 1;
      calls.push("estimate");
      if (estimateCalls === 1) {
        return HttpResponse.json(
          {
            detail:
              "Gemini временно перегружен. Фото сохранены, попробуйте повторить позже.",
          },
          { status: 503 },
        );
      }
      return HttpResponse.json({
        meal_id: "meal-1",
        suggested_items: [
          {
            name: "Retry meal",
            carbs_g: 12,
            protein_g: 8,
            fat_g: 4,
            fiber_g: 1,
            kcal: 120,
            confidence: 0.7,
            confidence_reason: "Retry succeeded.",
            source_kind: "photo_estimate",
            calculation_method: "visual_estimate_gemini_mid",
            assumptions: [],
            evidence: {},
            warnings: [],
            position: 0,
          },
        ],
        suggested_totals: {
          total_carbs_g: 12,
          total_protein_g: 8,
          total_fat_g: 4,
          total_fiber_g: 1,
          total_kcal: 120,
        },
        gemini_notes: "",
        image_quality_warnings: [],
        reference_detected: "none",
        ai_run_id: "ai-run-1",
      });
    }),
  );

  render(<App />);
  fireEvent.paste(commandInput(), {
    clipboardData: {
      files: [new File(["image"], "meal.jpg", { type: "image/jpeg" })],
    },
  });
  await user.click(screen.getByRole("button", { name: /Оценить/ }));

  expect(
    await screen.findByText(
      "Gemini временно перегружен. Фото сохранены, попробуйте повторить позже.",
    ),
  ).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Повторить оценку/ }));

  await screen.findByDisplayValue("Retry meal");
  expect(calls).toEqual(["create", "upload", "estimate", "estimate"]);
});

test("photo estimate panel shows source photo and label calculation history", async () => {
  configureApi();
  const user = userEvent.setup();

  server.use(
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
            name: "Бисквит-сэндвич",
            grams: 60,
            serving_text: "×2 упаковки · 30 г каждая",
            carbs_g: 37.2,
            protein_g: 2.7,
            fat_g: 9.6,
            fiber_g: 0,
            kcal: 246,
            confidence: 0.9,
            confidence_reason: "Этикетка и масса видны.",
            source_kind: "label_calc",
            calculation_method: "label_split_visible_weight_backend_calc",
            assumptions: ["обе упаковки считаются одинаковым продуктом"],
            evidence: {},
            warnings: [],
            position: 0,
          },
        ],
        suggested_totals: {
          total_carbs_g: 37.2,
          total_protein_g: 2.7,
          total_fat_g: 9.6,
          total_fiber_g: 0,
          total_kcal: 246,
        },
        calculation_breakdowns: [
          {
            position: 0,
            name: "Бисквит-сэндвич",
            count_detected: 2,
            net_weight_per_unit_g: 30,
            total_weight_g: 60,
            nutrition_per_100g: {
              carbs_g: 62,
              protein_g: 4.5,
              fat_g: 16,
              fiber_g: null,
              kcal: 410,
            },
            calculated_per_unit: {
              carbs_g: 18.6,
              protein_g: 1.4,
              fat_g: 4.8,
              fiber_g: null,
              kcal: 123,
            },
            calculated_total: {
              carbs_g: 37.2,
              protein_g: 2.7,
              fat_g: 9.6,
              fiber_g: 0,
              kcal: 246,
            },
            calculation_steps: [
              "1 упаковка = 30 г",
              "2 упаковки = 60 г",
              "углеводы: 62 × 60 / 100 = 37.2 г",
            ],
            evidence: [
              "найдено 2 одинаковые упаковки",
              "масса нетто 30 г видна на другой упаковке",
            ],
            assumptions: ["обе упаковки считаются одинаковым продуктом"],
          },
        ],
        gemini_notes: "",
        image_quality_warnings: [],
        reference_detected: "none",
        ai_run_id: "ai-run-1",
      }),
    ),
  );

  render(<App />);
  fireEvent.paste(commandInput(), {
    clipboardData: {
      files: [new File(["image"], "candy.jpg", { type: "image/jpeg" })],
    },
  });
  await user.click(screen.getByRole("button", { name: "Оценить" }));

  expect(
    await screen.findByRole("heading", { name: "Бисквит-сэндвич" }),
  ).toBeInTheDocument();
  expect(await screen.findByAltText("фото к оценке")).toBeInTheDocument();
  expect(screen.getByText("×2 упаковки · 30 г каждая")).toBeInTheDocument();
  expect(screen.getByText("За 1 шт.")).toBeInTheDocument();
  expect(screen.getByText("Итого")).toBeInTheDocument();
  expect(screen.getByText("Как посчитано")).toBeInTheDocument();
  expect(
    screen.getByText("углеводы: 62 × 60 / 100 = 37.2 г"),
  ).toBeInTheDocument();
  expect(
    screen.getAllByText("обе упаковки считаются одинаковым продуктом").length,
  ).toBeGreaterThan(0);
});

test("multi-photo estimate shows separate draft items with their source photos", async () => {
  configureApi();
  const user = userEvent.setup();
  server.use(
    http.post("http://api.test/meals/:mealId/estimate_and_save_draft", () =>
      HttpResponse.json({
        meal_id: "meal-1",
        source_photos: [
          {
            id: "photo-1",
            index: 1,
            url: "/photos/photo-1/file",
            thumbnail_url: "/photos/photo-1/file",
            original_filename: "drink.jpg",
          },
          {
            id: "photo-2",
            index: 2,
            url: "/photos/photo-2/file",
            thumbnail_url: "/photos/photo-2/file",
            original_filename: "wrap.jpg",
          },
        ],
        suggested_items: [
          {
            name: "Напиток",
            grams: 449,
            serving_text: "449 мл",
            carbs_g: 0,
            protein_g: 0,
            fat_g: 0,
            fiber_g: 0,
            kcal: 0,
            confidence: 0.82,
            confidence_reason: "Этикетка напитка читается.",
            source_kind: "label_calc",
            calculation_method: "label_assumed_weight_backend_calc",
            assumptions: ["объём принят по банке"],
            evidence: {
              source_photo_ids: ["photo-1"],
              primary_photo_id: "photo-1",
              source_photo_indices: [1],
              item_type: "drink",
              evidence_text: ["углеводы видны на этикетке"],
            },
            warnings: [],
            photo_id: "photo-1",
            position: 0,
          },
          {
            name: "Лаваш с курицей",
            grams: 240,
            carbs_g: 34,
            protein_g: 24,
            fat_g: 15,
            fiber_g: 2.5,
            kcal: 375,
            confidence: 0.64,
            confidence_reason: "Вес оценён визуально.",
            source_kind: "photo_estimate",
            calculation_method: "visual_estimate_gemini_mid",
            assumptions: ["вес оценён визуально"],
            evidence: {
              source_photo_ids: ["photo-2"],
              primary_photo_id: "photo-2",
              source_photo_indices: [2],
              item_type: "plated_food",
              evidence_text: ["видны курица, овощи и лаваш"],
            },
            warnings: [],
            photo_id: "photo-2",
            position: 1,
          },
        ],
        suggested_totals: {
          total_carbs_g: 34,
          total_protein_g: 24,
          total_fat_g: 15,
          total_fiber_g: 2.5,
          total_kcal: 375,
        },
        calculation_breakdowns: [],
        gemini_notes: "Two items.",
        image_quality_warnings: [],
        reference_detected: "none",
        ai_run_id: "ai-run-1",
        raw_gemini_response: null,
        created_drafts: [
          {
            meal_id: "meal-drink",
            title: "Напиток",
            source_photo_id: "photo-1",
            thumbnail_url: "/photos/photo-1/file",
            item: {
              name: "Напиток",
              grams: 449,
              carbs_g: 0,
              protein_g: 0,
              fat_g: 0,
              fiber_g: 0,
              kcal: 0,
              confidence: 0.82,
              confidence_reason: "Этикетка напитка читается.",
              source_kind: "label_calc",
              calculation_method: "label_assumed_weight_backend_calc",
              assumptions: ["объём принят по банке"],
              evidence: {
                source_photo_ids: ["photo-1"],
                primary_photo_id: "photo-1",
                source_photo_indices: [1],
                item_type: "drink",
              },
              warnings: [],
              photo_id: "photo-1",
              position: 0,
            },
            totals: {
              total_carbs_g: 0,
              total_protein_g: 0,
              total_fat_g: 0,
              total_fiber_g: 0,
              total_kcal: 0,
            },
          },
          {
            meal_id: "meal-wrap",
            title: "Лаваш с курицей",
            source_photo_id: "photo-2",
            thumbnail_url: "/photos/photo-2/file",
            item: {
              name: "Лаваш с курицей",
              grams: 240,
              carbs_g: 34,
              protein_g: 24,
              fat_g: 15,
              fiber_g: 2.5,
              kcal: 375,
              confidence: 0.64,
              confidence_reason: "Вес оценён визуально.",
              source_kind: "photo_estimate",
              calculation_method: "visual_estimate_gemini_mid",
              assumptions: ["вес оценён визуально"],
              evidence: {
                source_photo_ids: ["photo-2"],
                primary_photo_id: "photo-2",
                source_photo_indices: [2],
                item_type: "plated_food",
              },
              warnings: [],
              photo_id: "photo-2",
              position: 0,
            },
            totals: {
              total_carbs_g: 34,
              total_protein_g: 24,
              total_fat_g: 15,
              total_fiber_g: 2.5,
              total_kcal: 375,
            },
          },
        ],
      }),
    ),
  );

  render(<App />);
  fireEvent.paste(commandInput(), {
    clipboardData: {
      files: [
        new File(["image"], "drink.jpg", { type: "image/jpeg" }),
        new File(["image"], "wrap.jpg", { type: "image/jpeg" }),
      ],
    },
  });
  await user.click(screen.getByRole("button", { name: "Оценить" }));

  expect(await screen.findByText("Создано черновиков: 2")).toBeInTheDocument();
  expect(screen.getByText("Напиток")).toBeInTheDocument();
  expect(screen.getByText("Лаваш с курицей")).toBeInTheDocument();
  expect(screen.getAllByText(/Фото \/ черновик/)).toHaveLength(2);
  expect(await screen.findByAltText("Напиток фото")).toBeInTheDocument();
  expect(
    await screen.findByAltText("Лаваш с курицей фото"),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Сохранить все" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Удалить все черновики" }),
  ).toBeInTheDocument();
});

test("save calls accept", async () => {
  configureApi();
  const user = userEvent.setup();
  let acceptCalled = false;

  server.use(
    http.post("http://api.test/meals/:mealId/accept", async () => {
      acceptCalled = true;
      return HttpResponse.json({});
    }),
  );

  render(<App />);
  fireEvent.paste(commandInput(), {
    clipboardData: {
      files: [new File(["image"], "meal.jpg", { type: "image/jpeg" })],
    },
  });
  await user.click(screen.getByRole("button", { name: "Оценить" }));
  await screen.findByDisplayValue("Chicken and potatoes");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(acceptCalled).toBe(true));
});

test("photo draft can be reopened from journal and accepted", async () => {
  configureApi();
  const user = userEvent.setup();
  let currentMeal: Record<string, unknown> | null = null;
  let acceptedBody: { items?: Array<Record<string, unknown>> } | null = null;

  const draftItem = {
    id: "item-draft-1",
    meal_id: "meal-draft-1",
    name: "Бисквит-сэндвич",
    brand: null,
    grams: 60,
    serving_text: "×2 упаковки · 30 г каждая",
    carbs_g: 37.2,
    protein_g: 2.7,
    fat_g: 9.6,
    fiber_g: 0,
    kcal: 246,
    confidence: 0.9,
    confidence_reason: "Этикетка читается.",
    source_kind: "label_calc",
    calculation_method: "label_split_visible_weight_backend_calc",
    assumptions: ["обе упаковки считаются одинаковым продуктом"],
    evidence: {
      primary_photo_id: "photo-draft-1",
      source_photo_ids: ["photo-draft-1"],
      source_photo_indices: [1],
      evidence_text: ["масса нетто видна на фото"],
    },
    warnings: [],
    pattern_id: null,
    product_id: null,
    photo_id: "photo-draft-1",
    image_url: null,
    image_cache_path: null,
    source_image_url: null,
    position: 0,
    created_at: "2026-04-28T10:00:00.000Z",
    updated_at: "2026-04-28T10:00:00.000Z",
  };

  const draftPhoto = {
    id: "photo-draft-1",
    meal_id: "meal-draft-1",
    path: "2026/04/photo-draft-1.jpg",
    original_filename: "candy.jpg",
    content_type: "image/jpeg",
    taken_at: null,
    scenario: "label_full",
    has_reference_object: false,
    reference_kind: "none",
    gemini_response_raw: null,
    created_at: "2026-04-28T10:00:00.000Z",
  };

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: currentMeal ? [currentMeal] : [],
        total: currentMeal ? 1 : 0,
        limit: 100,
        offset: 0,
      }),
    ),
    http.post("http://api.test/meals", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      currentMeal = mealFixture({
        ...body,
        id: "meal-draft-1",
        title: "Еда по фото",
        status: "draft",
        source: "photo",
        total_carbs_g: 0,
        total_protein_g: 0,
        total_fat_g: 0,
        total_fiber_g: 0,
        total_kcal: 0,
        items: [],
        photos: [],
      });
      return HttpResponse.json(currentMeal, { status: 201 });
    }),
    http.post("http://api.test/meals/:mealId/photos", () =>
      HttpResponse.json(draftPhoto, { status: 201 }),
    ),
    http.post("http://api.test/meals/:mealId/estimate_and_save_draft", () => {
      currentMeal = mealFixture({
        id: "meal-draft-1",
        title: "Еда по фото",
        status: "draft",
        source: "photo",
        total_carbs_g: 37.2,
        total_protein_g: 2.7,
        total_fat_g: 9.6,
        total_fiber_g: 0,
        total_kcal: 246,
        confidence: 0.9,
        items: [draftItem],
        photos: [draftPhoto],
      });
      return HttpResponse.json({
        meal_id: "meal-draft-1",
        source_photos: [
          {
            id: "photo-draft-1",
            index: 1,
            url: "/photos/photo-draft-1/file",
            thumbnail_url: "/photos/photo-draft-1/file",
            original_filename: "candy.jpg",
          },
        ],
        suggested_items: [
          {
            name: "Бисквит-сэндвич",
            grams: 60,
            carbs_g: 37.2,
            protein_g: 2.7,
            fat_g: 9.6,
            fiber_g: 0,
            kcal: 246,
            confidence: 0.9,
            confidence_reason: "Этикетка читается.",
            source_kind: "label_calc",
            calculation_method: "label_split_visible_weight_backend_calc",
            assumptions: ["обе упаковки считаются одинаковым продуктом"],
            evidence: {
              primary_photo_id: "photo-draft-1",
              source_photo_ids: ["photo-draft-1"],
              source_photo_indices: [1],
              evidence_text: ["масса нетто видна на фото"],
            },
            warnings: [],
            photo_id: "photo-draft-1",
            position: 0,
          },
        ],
        suggested_totals: {
          total_carbs_g: 37.2,
          total_protein_g: 2.7,
          total_fat_g: 9.6,
          total_fiber_g: 0,
          total_kcal: 246,
        },
        calculation_breakdowns: [],
        gemini_notes: "",
        image_quality_warnings: [],
        reference_detected: "none",
        ai_run_id: "ai-run-1",
        raw_gemini_response: null,
      });
    }),
    http.post("http://api.test/meals/:mealId/accept", async ({ request }) => {
      acceptedBody = (await request.json()) as {
        items?: Array<Record<string, unknown>>;
      };
      currentMeal = {
        ...(currentMeal ?? {}),
        status: "accepted",
        title: "Бисквит-сэндвич",
        items: acceptedBody.items ?? [],
      };
      return HttpResponse.json(currentMeal);
    }),
  );

  render(<App />);
  fireEvent.paste(commandInput(), {
    clipboardData: {
      files: [new File(["image"], "candy.jpg", { type: "image/jpeg" })],
    },
  });
  await user.click(screen.getByRole("button", { name: "Оценить" }));
  expect(
    await screen.findByDisplayValue("Бисквит-сэндвич"),
  ).toBeInTheDocument();

  await user.click(
    await screen.findByRole("button", { name: /Бисквит-сэндвич/i }),
  );
  expect(screen.getByDisplayValue("Бисквит-сэндвич")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Сохранить" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Отменить" })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() =>
    expect(acceptedBody?.items?.[0]?.name).toBe("Бисквит-сэндвич"),
  );
  await waitFor(() =>
    expect((currentMeal as { status?: string } | null)?.status).toBe(
      "accepted",
    ),
  );
});

test("discard calls discard", async () => {
  configureApi();
  const user = userEvent.setup();
  let discardCalled = false;

  server.use(
    http.post("http://api.test/meals/:mealId/discard", async () => {
      discardCalled = true;
      return HttpResponse.json({});
    }),
  );

  render(<App />);
  fireEvent.paste(commandInput(), {
    clipboardData: {
      files: [new File(["image"], "meal.jpg", { type: "image/jpeg" })],
    },
  });
  await user.click(screen.getByRole("button", { name: "Оценить" }));
  await screen.findByDisplayValue("Chicken and potatoes");
  await user.click(screen.getByRole("button", { name: "Отменить" }));

  await waitFor(() => expect(discardCalled).toBe(true));
});

test("low-confidence meal renders check label", async () => {
  configureApi();

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [
          {
            id: "meal-low",
            eaten_at: "2026-04-28T10:00:00Z",
            title: "Plated estimate",
            note: null,
            status: "draft",
            source: "photo",
            total_carbs_g: 34,
            total_protein_g: 28,
            total_fat_g: 12,
            total_fiber_g: 4,
            total_kcal: 360,
            confidence: 0.55,
            nightscout_synced_at: null,
            nightscout_id: null,
            created_at: "2026-04-28T10:00:00Z",
            updated_at: "2026-04-28T10:00:00Z",
            items: [],
            photos: [],
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
  );

  render(<App />);

  expect(await screen.findByText("проверить")).toBeInTheDocument();
});

test("database route lists food items and opens detail panel", async () => {
  configureApi();
  databaseRoute();

  render(<App />);

  expect(await screen.findByText("Whopper")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Whopper/i }));

  expect(screen.getByRole("heading", { name: "Whopper" })).toBeInTheDocument();
  expect(screen.getByText("bk:whopper")).toBeInTheDocument();
  expect(screen.getByText("Натрий")).toBeInTheDocument();
});

test("database search finds Whopper by Russian alias", async () => {
  configureApi();
  databaseRoute();

  render(<App />);
  await userEvent.type(screen.getByLabelText("Поиск по базе"), "воппер");

  expect(await screen.findByText("Whopper")).toBeInTheDocument();
  expect(screen.queryByText("Protein Drink")).not.toBeInTheDocument();
});

test("database import button opens import panel", async () => {
  configureApi();
  databaseRoute();

  render(<App />);
  await userEvent.click(screen.getByRole("button", { name: "Импорт" }));

  expect(
    screen.getByRole("heading", { name: "Импорт базы" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText("backend import endpoint пока не реализован."),
  ).toBeInTheDocument();
});

test("database broken image falls back to placeholder", async () => {
  configureApi();
  databaseRoute();

  render(<App />);
  fireEvent.error(await screen.findByAltText("Whopper фото"));

  expect(screen.getByLabelText("изображение недоступно")).toBeInTheDocument();
});

test("database renders authenticated backend photo images", async () => {
  configureApi();
  databaseRoute();
  let authorizationHeader = "";

  server.use(
    http.get("http://api.test/database/items", () =>
      HttpResponse.json({
        items: [
          {
            id: "product-photo-1",
            kind: "product",
            prefix: null,
            key: null,
            token: null,
            display_name: "Бисквит-сэндвич",
            subtitle: "Крокотыш · label_calc",
            image_url: "/photos/photo-1/file",
            image_cache_path: null,
            carbs_g: 18.6,
            protein_g: 1.3,
            fat_g: 4.8,
            fiber_g: null,
            kcal: 123,
            default_grams: 30,
            usage_count: 1,
            last_used_at: null,
            source_name: "Крокотыш",
            source_url: null,
            source_confidence: null,
            is_verified: false,
            aliases: ["Бисквит-сэндвич"],
            nutrients_json: {},
            quality_warnings: [],
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
    http.get("http://api.test/photos/photo-1/file", ({ request }) => {
      authorizationHeader = request.headers.get("authorization") ?? "";
      return HttpResponse.text("image-bytes", {
        headers: { "Content-Type": "image/jpeg" },
      });
    }),
  );

  render(<App />);

  expect(
    await screen.findByAltText("Бисквит-сэндвич фото"),
  ).toBeInTheDocument();
  await waitFor(() => expect(authorizationHeader).toBe("Bearer dev-token"));
});

test("database renders authenticated product image files", async () => {
  configureApi();
  databaseRoute();
  let authorizationHeader = "";

  server.use(
    http.get("http://api.test/database/items", () =>
      HttpResponse.json({
        items: [
          {
            id: "product-photo-1",
            kind: "product",
            prefix: null,
            key: null,
            token: null,
            display_name: "Test Product",
            subtitle: "label_calc",
            image_url: "/products/product-photo-1/image/file",
            image_cache_path: null,
            carbs_g: 18,
            protein_g: 3,
            fat_g: 5,
            fiber_g: null,
            kcal: 130,
            default_grams: 40,
            usage_count: 1,
            last_used_at: null,
            source_name: "label_calc",
            source_url: null,
            source_confidence: null,
            is_verified: false,
            aliases: ["test product"],
            nutrients_json: {},
            quality_warnings: [],
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
    http.get("http://api.test/products/product-photo-1/image/file", ({ request }) => {
      authorizationHeader = request.headers.get("authorization") ?? "";
      return HttpResponse.text("product-image-bytes", {
        headers: { "Content-Type": "image/png" },
      });
    }),
  );

  render(<App />);

  await waitFor(() => expect(authorizationHeader).toBe("Bearer dev-token"));
  expect(screen.getByAltText(/Test Product/)).toBeInTheDocument();
});

test("journal meal row shows backend thumbnail", async () => {
  configureApi();

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [
          mealFixture({
            title: "Whopper",
            thumbnail_url: "https://example.test/whopper.png",
            items: [
              {
                ...(mealFixture().items as Array<Record<string, unknown>>)[0],
                name: "Whopper",
                image_url: "https://example.test/whopper.png",
                source_image_url: "https://example.test/whopper.png",
              },
            ],
          }),
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
  );

  render(<App />);

  expect(await screen.findByAltText("Whopper фото")).toBeInTheDocument();
});

test("journal row prefers database product image over original source photo", async () => {
  configureApi();
  const user = userEvent.setup();
  let productImageRequested = false;
  let sourcePhotoRequested = false;

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [
          mealFixture({
            title: "Protein brownie Shagi",
            source: "photo",
            thumbnail_url: "/photos/source-photo/file",
            photos: [
              {
                id: "source-photo",
                meal_id: "meal-1",
                path: "2026/04/source-photo.jpg",
                original_filename: "label.jpg",
                content_type: "image/jpeg",
                taken_at: null,
                scenario: "label_full",
                has_reference_object: false,
                reference_kind: "none",
                gemini_response_raw: null,
                created_at: "2026-04-28T10:00:00.000Z",
              },
            ],
            items: [
              {
                ...(mealFixture().items as Array<Record<string, unknown>>)[0],
                name: "Protein brownie Shagi",
                source_kind: "label_calc",
                product_id: "product-brownie",
                photo_id: "source-photo",
                image_url: "/products/product-brownie/image/file",
                source_image_url: "/products/product-brownie/image/file",
              },
            ],
          }),
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
    http.get("http://api.test/products/product-brownie/image/file", () => {
      productImageRequested = true;
      return HttpResponse.text("product-image-bytes", {
        headers: { "Content-Type": "image/png" },
      });
    }),
    http.get("http://api.test/photos/source-photo/file", () => {
      sourcePhotoRequested = true;
      return HttpResponse.text("source-photo-bytes", {
        headers: { "Content-Type": "image/jpeg" },
      });
    }),
  );

  render(<App />);

  expect(await screen.findByAltText(/Protein brownie Shagi/)).toBeInTheDocument();
  await waitFor(() => expect(productImageRequested).toBe(true));
  expect(sourcePhotoRequested).toBe(false);

  await user.click(screen.getByText("Protein brownie Shagi"));

  expect(
    screen.getByRole("heading", { name: /Protein brownie Shagi/ }),
  ).toBeInTheDocument();
  expect(sourcePhotoRequested).toBe(false);
});

test("journal row and details make multi-unit quantity explicit", async () => {
  configureApi();

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [
          mealFixture({
            id: "meal-biscuit-x2",
            title: "Бисквит-сэндвич",
            source: "photo",
            total_carbs_g: 37.2,
            total_protein_g: 2.7,
            total_fat_g: 9.6,
            total_fiber_g: 0,
            total_kcal: 246,
            items: [
              {
                ...(mealFixture().items as Array<Record<string, unknown>>)[0],
                id: "item-biscuit-x2",
                meal_id: "meal-biscuit-x2",
                name: "Бисквит-сэндвич",
                grams: 60,
                serving_text: "×2 упаковки · 30 г каждая",
                carbs_g: 37.2,
                protein_g: 2.7,
                fat_g: 9.6,
                fiber_g: 0,
                kcal: 246,
                source_kind: "label_calc",
                calculation_method: "label_split_visible_weight_backend_calc",
                evidence: {
                  count_detected: 2,
                  net_weight_per_unit_g: 30,
                  total_weight_g: 60,
                },
              },
            ],
          }),
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    ),
  );

  render(<App />);

  await userEvent.click(await screen.findByText("Бисквит-сэндвич ×2"));

  expect(screen.getByText(/2 упаковки по 30 г/)).toBeInTheDocument();
  expect(screen.getByText("Количество")).toBeInTheDocument();
  expect(screen.getByText("2 упаковки")).toBeInTheDocument();
  expect(screen.getByText(/2 × 30 г/)).toBeInTheDocument();
  expect(screen.getByText(/60 г всего/)).toBeInTheDocument();
  expect(screen.getByText("На 1 упаковку")).toBeInTheDocument();
  expect(screen.getByText("Итого")).toBeInTheDocument();
  expect(screen.getByText("18.6")).toBeInTheDocument();
  expect(screen.getByText("37.2")).toBeInTheDocument();
  expect(screen.getAllByText("246").length).toBeGreaterThan(0);
});

test("feed meal row shows backend thumbnail", async () => {
  configureApi();
  feedRoute();

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [
          mealFixture({
            title: "Whopper",
            thumbnail_url: "https://example.test/whopper.png",
          }),
        ],
        total: 1,
        limit: 50,
        offset: 0,
      }),
    ),
  );

  render(<App />);

  expect(await screen.findByAltText("Whopper фото")).toBeInTheDocument();
});

test("feed row shows multi-unit quantity in title and subtitle", async () => {
  configureApi();
  feedRoute();

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [
          mealFixture({
            id: "meal-feed-biscuit-x2",
            title: "Бисквит-сэндвич",
            source: "photo",
            total_carbs_g: 37.2,
            total_protein_g: 2.7,
            total_fat_g: 9.6,
            total_fiber_g: 0,
            total_kcal: 246,
            items: [
              {
                ...(mealFixture().items as Array<Record<string, unknown>>)[0],
                id: "item-feed-biscuit-x2",
                meal_id: "meal-feed-biscuit-x2",
                name: "Бисквит-сэндвич",
                grams: 60,
                serving_text: "×2 упаковки · 30 г каждая",
                carbs_g: 37.2,
                protein_g: 2.7,
                fat_g: 9.6,
                fiber_g: 0,
                kcal: 246,
                source_kind: "label_calc",
                calculation_method: "label_split_visible_weight_backend_calc",
                evidence: {
                  count_detected: 2,
                  net_weight_per_unit_g: 30,
                  total_weight_g: 60,
                },
              },
            ],
          }),
        ],
        total: 1,
        limit: 50,
        offset: 0,
      }),
    ),
  );

  render(<App />);

  expect(await screen.findByText("Бисквит-сэндвич ×2")).toBeInTheDocument();
  expect(screen.getByText(/2 упаковки по 30 г/)).toBeInTheDocument();
});

test("feed hides discarded meals by default and can show them explicitly", async () => {
  configureApi();
  feedRoute();

  const acceptedMeal = mealFixture({
    id: "meal-accepted",
    title: "Принятая еда",
  });
  const discardedMeal = mealFixture({
    id: "meal-discarded",
    status: "discarded",
    title: "Отмененная еда по фото",
  });

  server.use(
    http.get("http://api.test/meals", ({ request }) => {
      const status = new URL(request.url).searchParams.get("status");
      return HttpResponse.json({
        items: status === "discarded" ? [discardedMeal] : [acceptedMeal, discardedMeal],
        total: status === "discarded" ? 1 : 2,
        limit: 50,
        offset: 0,
      });
    }),
  );

  render(<App />);

  expect(await screen.findByText("Принятая еда")).toBeInTheDocument();
  expect(screen.queryByText("Отмененная еда по фото")).not.toBeInTheDocument();

  await userEvent.selectOptions(
    screen.getByLabelText("Фильтр статуса"),
    "discarded",
  );

  expect(await screen.findByText("Отмененная еда по фото")).toBeInTheDocument();
});

test("feed groups meals by day", async () => {
  configureApi();
  feedRoute();

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [
          mealFixture({
            id: "meal-today",
            eaten_at: "2026-04-28T10:00:00.000Z",
            title: "Coffee",
          }),
          mealFixture({
            id: "meal-yesterday",
            eaten_at: "2026-04-27T10:00:00.000Z",
            title: "Protein bar",
          }),
        ],
        total: 2,
        limit: 50,
        offset: 0,
      }),
    ),
  );

  render(<App />);

  expect(
    await screen.findByRole("heading", { name: /вторник, 28 апреля/i }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: /понедельник, 27 апреля/i }),
  ).toBeInTheDocument();
});

test("feed renders computed Nightscout food episode", async () => {
  configureApi();
  feedRoute();
  let importCalled = 0;
  const mealWrap = mealFixture({
    id: "meal-wrap",
    eaten_at: "2026-04-28T12:00:00",
    title: "Лаваш с курицей",
    total_carbs_g: 42,
    total_kcal: 510,
  });
  const mealCola = mealFixture({
    id: "meal-cola",
    eaten_at: "2026-04-28T12:20:00",
    title: "Кола оригинал",
    total_carbs_g: 26,
    total_kcal: 104,
  });

  server.use(
    http.get("http://api.test/settings/nightscout", () =>
      HttpResponse.json({
        enabled: true,
        configured: true,
        connected: true,
        url: "https://nightscout.example",
        secret_is_set: true,
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
    http.post("http://api.test/nightscout/import", () => {
      importCalled += 1;
      return HttpResponse.json({
        from_datetime: "2026-04-28T00:00:00",
        to_datetime: "2026-04-28T23:59:59",
        glucose_imported: 3,
        insulin_imported: 1,
        glucose_total: 3,
        insulin_total: 1,
        last_error: null,
      });
    }),
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [mealWrap, mealCola],
        total: 2,
        limit: 50,
        offset: 0,
      }),
    ),
    http.get("http://api.test/timeline", () =>
      HttpResponse.json({
        from_datetime: "2026-04-28T00:00:00",
        to_datetime: "2026-04-28T23:59:59",
        episodes: [
          {
            id: "episode-wrap-cola",
            start_at: "2026-04-28T12:00:00",
            end_at: "2026-04-28T12:20:00",
            title: "Пищевой эпизод",
            meals: [mealWrap, mealCola],
            insulin: [
              {
                timestamp: "2026-04-28T12:05:00",
                insulin_units: 4,
                eventType: "Meal Bolus",
                insulin_type: "rapid",
                enteredBy: "nightscout",
                notes: null,
                nightscout_id: "insulin-1",
              },
            ],
            glucose: [
              {
                timestamp: "2026-04-28T11:55:00",
                value: 5.5,
                unit: "mmol/L",
                trend: "Flat",
                source: "Nightscout",
              },
              {
                timestamp: "2026-04-28T12:25:00",
                value: 8.8,
                unit: "mmol/L",
                trend: "FortyFiveUp",
                source: "Nightscout",
              },
            ],
            glucose_summary: {
              before_value: 5.5,
              peak_value: 8.8,
              latest_value: 8.8,
              min_value: 5.5,
              max_value: 8.8,
            },
            total_carbs_g: 68,
            total_kcal: 614,
          },
        ],
        ungrouped_insulin: [],
      }),
    ),
  );

  render(<App />);

  expect(await screen.findByText("Приём пищи")).toBeInTheDocument();
  expect(screen.getByText("Лаваш с курицей")).toBeInTheDocument();
  expect(screen.getByText("Кола оригинал")).toBeInTheDocument();
  expect(screen.getByText("Инсулин из Nightscout")).toBeInTheDocument();
  expect(
    screen.getByRole("img", {
      name: "Мини-график глюкозы вокруг пищевого эпизода",
    }),
  ).toBeInTheDocument();
  await waitFor(() => expect(importCalled).toBeGreaterThan(0));
});

test("feed keeps food episode grouping when Nightscout is not configured", async () => {
  configureApi();
  feedRoute();
  const firstMeal = mealFixture({
    id: "meal-photo-a",
    eaten_at: "2026-04-28T12:00:00",
    title: "Кусочек торта",
    total_carbs_g: 18,
    total_kcal: 180,
  });
  const secondMeal = mealFixture({
    id: "meal-photo-b",
    eaten_at: "2026-04-28T12:12:00",
    title: "Кола оригинал",
    total_carbs_g: 26,
    total_kcal: 104,
  });

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [firstMeal, secondMeal],
        total: 2,
        limit: 50,
        offset: 0,
      }),
    ),
    http.get("http://api.test/timeline", () =>
      HttpResponse.json({
        from_datetime: "2026-04-28T00:00:00",
        to_datetime: "2026-04-28T23:59:59",
        episodes: [
          {
            id: "episode-photo-items",
            start_at: "2026-04-28T12:00:00",
            end_at: "2026-04-28T12:12:00",
            title: "Пищевой эпизод",
            meals: [firstMeal, secondMeal],
            insulin: [],
            glucose: [],
            glucose_summary: {
              before_value: null,
              peak_value: null,
              latest_value: null,
              min_value: null,
              max_value: null,
            },
            total_carbs_g: 44,
            total_kcal: 284,
          },
        ],
        ungrouped_insulin: [],
      }),
    ),
  );

  render(<App />);

  expect(await screen.findByText("Приём пищи")).toBeInTheDocument();
  expect(screen.getByText("Кусочек торта")).toBeInTheDocument();
  expect(screen.getByText("Кола оригинал")).toBeInTheDocument();
  expect(screen.getByText(/2 события · 284 ккал · 44 г углеводов/)).toBeInTheDocument();
});

test("feed paginates with cursor", async () => {
  configureApi();
  feedRoute();
  const requestedTo: Array<string | null> = [];
  const firstPage = Array.from({ length: 50 }, (_, index) =>
    mealFixture({
      id: `meal-${index}`,
      eaten_at: new Date(Date.UTC(2026, 3, 28, 12, 0 - index, 0)).toISOString(),
      title: `Meal ${index}`,
    }),
  );

  server.use(
    http.get("http://api.test/meals", ({ request }) => {
      const url = new URL(request.url);
      requestedTo.push(url.searchParams.get("to"));
      if (requestedTo.length === 1) {
        return HttpResponse.json({
          items: firstPage,
          total: 51,
          limit: 50,
          offset: 0,
        });
      }
      return HttpResponse.json({
        items: [
          mealFixture({
            id: "meal-older",
            eaten_at: "2026-04-27T09:00:00.000Z",
            title: "Older meal",
          }),
        ],
        total: 51,
        limit: 50,
        offset: 0,
      });
    }),
  );

  render(<App />);

  await screen.findByText("Meal 49");
  await userEvent.click(screen.getByRole("button", { name: "Загрузить еще" }));

  expect(await screen.findByText("Older meal")).toBeInTheDocument();
  expect(requestedTo[1]).toBeTruthy();
});

test("feed q search calls meals query", async () => {
  configureApi();
  feedRoute();
  const queries: Array<string | null> = [];

  server.use(
    http.get("http://api.test/meals", ({ request }) => {
      queries.push(new URL(request.url).searchParams.get("q"));
      return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
    }),
  );

  render(<App />);
  await userEvent.type(screen.getByLabelText("Поиск по еде"), "coffee");

  await waitFor(() => expect(queries).toContain("coffee"));
});

test("feed date and status filters call meals query", async () => {
  configureApi();
  feedRoute();
  let latestUrl: URL | null = null;

  server.use(
    http.get("http://api.test/meals", ({ request }) => {
      latestUrl = new URL(request.url);
      return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
    }),
  );

  render(<App />);
  fireEvent.change(screen.getByLabelText("Дата от"), {
    target: { value: "2026-04-01" },
  });
  fireEvent.change(screen.getByLabelText("Дата до"), {
    target: { value: "2026-04-30" },
  });
  await userEvent.selectOptions(
    screen.getByLabelText("Фильтр статуса"),
    "draft",
  );

  await waitFor(() => {
    expect(latestUrl?.searchParams.get("from")).toBeTruthy();
    expect(latestUrl?.searchParams.get("to")).toBeTruthy();
    expect(latestUrl?.searchParams.get("status")).toBe("draft");
  });
});

test("feed detail panel opens and duplicate uses create meal fallback", async () => {
  configureApi();
  feedRoute();
  let createdBody: Record<string, unknown> | null = null;

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [mealFixture()],
        total: 1,
        limit: 50,
        offset: 0,
      }),
    ),
    http.post("http://api.test/meals", async ({ request }) => {
      createdBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        mealFixture({ id: "meal-copy", ...createdBody }),
        { status: 201 },
      );
    }),
  );

  render(<App />);
  await userEvent.click(await screen.findByText("Coffee"));

  expect(screen.getByRole("heading", { name: "Coffee" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Повторить" }));

  await waitFor(() => expect(createdBody?.status).toBe("accepted"));
  const duplicated = createdBody as unknown as {
    eaten_at?: unknown;
    items?: Array<Record<string, unknown>>;
  };
  expect(duplicated.eaten_at).toEqual(expect.any(String));
  const copiedItems = duplicated.items;
  expect(copiedItems?.[0]).toMatchObject({
    name: "Coffee",
    carbs_g: 22,
    photo_id: null,
  });
});

test("feed detail panel repeats one item by new gram weight", async () => {
  configureApi();
  feedRoute();
  let copyBody: Record<string, unknown> | null = null;
  let copiedItemId: string | undefined;
  const cakeItem = {
    ...(mealFixture().items[0] as Record<string, unknown>),
    id: "cake-item-1",
    name: "Кусочек торта",
    grams: 117,
    carbs_g: 35.1,
    protein_g: 5.9,
    fat_g: 14,
    fiber_g: 1.2,
    kcal: 280,
  };
  const cakeMeal = mealFixture({
    id: "cake-meal-1",
    title: "Кусочек торта",
    total_carbs_g: 35.1,
    total_protein_g: 5.9,
    total_fat_g: 14,
    total_fiber_g: 1.2,
    total_kcal: 280,
    items: [cakeItem],
  });

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [cakeMeal],
        total: 1,
        limit: 50,
        offset: 0,
      }),
    ),
    http.post("http://api.test/meal_items/:itemId/copy_by_weight", async ({ params, request }) => {
      copiedItemId = String(params.itemId);
      copyBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        mealFixture({
          id: "cake-meal-copy",
          title: "Кусочек торта",
          eaten_at: copyBody.eaten_at,
          total_carbs_g: 38.1,
          total_kcal: 303.9,
          items: [
            {
              ...cakeItem,
              id: "cake-item-copy",
              grams: copyBody.grams,
              carbs_g: 38.1,
              kcal: 303.9,
            },
          ],
        }),
        { status: 201 },
      );
    }),
  );

  render(<App />);
  await userEvent.click(await screen.findByText("Кусочек торта"));
  expect(screen.getByText(/вручную \/ принято · 117 г/)).toBeInTheDocument();
  expect(screen.getByText("Повтор по весу")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Вес новой записи, г"), {
    target: { value: "127" },
  });
  await userEvent.click(screen.getByRole("button", { name: "Добавить 127 г" }));

  await waitFor(() => expect(copiedItemId).toBe("cake-item-1"));
  expect(copyBody).not.toBeNull();
  const finalBody = copyBody as unknown as Record<string, unknown>;
  expect(finalBody.grams).toBe(127);
  expect(finalBody.eaten_at).toEqual(expect.any(String));
});

test("feed detail panel repeats one recognized package by unit weight", async () => {
  configureApi();
  feedRoute();
  let copyBody: Record<string, unknown> | null = null;
  let copiedItemId: string | undefined;
  const halvaItem = {
    ...(mealFixture().items[0] as Record<string, unknown>),
    id: "halva-item-1",
    name: "Халва подсолнечная глазированная",
    brand: "Восточный гость",
    grams: 60,
    serving_text: "×3 упаковки · 20 г каждая",
    carbs_g: 28.2,
    protein_g: 6,
    fat_g: 21.6,
    fiber_g: 0,
    kcal: 330,
    source_kind: "label_calc",
    calculation_method: "label_split_visible_weight_backend_calc",
    evidence: {
      count_detected: 3,
      net_weight_per_unit_g: 20,
      total_weight_g: 60,
    },
  };
  const halvaMeal = mealFixture({
    id: "halva-meal-1",
    title: "Халва подсолнечная глазированная ×3",
    total_carbs_g: 28.2,
    total_protein_g: 6,
    total_fat_g: 21.6,
    total_fiber_g: 0,
    total_kcal: 330,
    items: [halvaItem],
  });

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [halvaMeal],
        total: 1,
        limit: 50,
        offset: 0,
      }),
    ),
    http.post("http://api.test/meal_items/:itemId/copy_by_weight", async ({ params, request }) => {
      copiedItemId = String(params.itemId);
      copyBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        mealFixture({
          id: "halva-meal-copy",
          title: "Халва подсолнечная глазированная",
          eaten_at: copyBody.eaten_at,
          total_carbs_g: 9.4,
          total_kcal: 110,
          items: [
            {
              ...halvaItem,
              id: "halva-item-copy",
              grams: copyBody.grams,
              carbs_g: 9.4,
              kcal: 110,
            },
          ],
        }),
        { status: 201 },
      );
    }),
  );

  render(<App />);
  await userEvent.click(
    await screen.findByText("Халва подсолнечная глазированная ×3"),
  );
  expect(screen.getByText("Быстро из распознанного количества")).toBeInTheDocument();

  await userEvent.click(
    screen.getByRole("button", { name: /Добавить 1 упаковку/ }),
  );

  await waitFor(() => expect(copiedItemId).toBe("halva-item-1"));
  expect(copyBody).not.toBeNull();
  const finalBody = copyBody as unknown as Record<string, unknown>;
  expect(finalBody.grams).toBe(20);
  expect(finalBody.eaten_at).toEqual(expect.any(String));
});

test("feed detail panel edits current item weight", async () => {
  configureApi();
  feedRoute();
  let patchedBody: Record<string, unknown> | null = null;
  let patchedItemId: string | undefined;
  const cakeItem = {
    ...(mealFixture().items[0] as Record<string, unknown>),
    id: "cake-item-1",
    name: "Кусочек торта",
    grams: 117,
    carbs_g: 35.1,
    protein_g: 5.9,
    fat_g: 14,
    fiber_g: 1.2,
    kcal: 280,
  };
  const cakeMeal = mealFixture({
    id: "cake-meal-1",
    title: "Кусочек торта",
    total_carbs_g: 35.1,
    total_protein_g: 5.9,
    total_fat_g: 14,
    total_fiber_g: 1.2,
    total_kcal: 280,
    items: [cakeItem],
  });

  server.use(
    http.get("http://api.test/meals", () =>
      HttpResponse.json({
        items: [cakeMeal],
        total: 1,
        limit: 50,
        offset: 0,
      }),
    ),
    http.patch("http://api.test/meal_items/:itemId", async ({ params, request }) => {
      patchedItemId = String(params.itemId);
      patchedBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        ...cakeItem,
        ...patchedBody,
        id: patchedItemId,
        meal_id: "cake-meal-1",
        serving_text: `${patchedBody.grams} г`,
        updated_at: "2026-04-28T10:10:00.000Z",
      });
    }),
  );

  render(<App />);
  await userEvent.click(await screen.findByText("Кусочек торта"));

  fireEvent.change(screen.getByLabelText("Вес текущей записи, г"), {
    target: { value: "127" },
  });
  await userEvent.click(screen.getByRole("button", { name: "Сохранить вес" }));

  await waitFor(() => expect(patchedItemId).toBe("cake-item-1"));
  expect(patchedBody).not.toBeNull();
  const finalPatchBody = patchedBody as unknown as Record<string, unknown>;
  expect(finalPatchBody.grams).toBe(127);
});

test("feed empty state says no meals yet", async () => {
  configureApi();
  feedRoute();

  render(<App />);

  expect(await screen.findByText("записей пока нет")).toBeInTheDocument();
});

test("stats KPI tiles match fixture", async () => {
  configureApi();
  statsRoute();
  useDashboardFixture();

  render(<App />);

  expect(await screen.findByText("углеводы сегодня")).toBeInTheDocument();
  expect(await screen.findByText("186")).toBeInTheDocument();
  expect(await screen.findByText("2140")).toBeInTheDocument();
  expect((await screen.findAllByText("5")).length).toBeGreaterThan(0);
  expect(await screen.findByText("4")).toBeInTheDocument();
  expect(
    await screen.findByText("среднее за неделю 152 г"),
  ).toBeInTheDocument();
});

test("stats range chart renders fixture days", async () => {
  configureApi();
  statsRoute();
  useDashboardFixture();

  render(<App />);

  await screen.findByRole("img", {
    name: "Углеводы по дням за последние 30 дней",
  });
  expect(screen.getAllByTestId("range-bar")).toHaveLength(3);
});

test("stats heatmap cell count is complete", async () => {
  configureApi();
  statsRoute();
  useDashboardFixture();

  render(<App />);

  await screen.findByRole("img", {
    name: "Тепловая карта еды по дням и часам",
  });
  expect(screen.getAllByTestId("heatmap-cell")).toHaveLength(168);
});

test("stats source breakdown percentages are calculated", async () => {
  configureApi();
  statsRoute();
  useDashboardFixture();

  render(<App />);

  expect(await screen.findByText("Источники данных")).toBeInTheDocument();
  expect(await screen.findByText("шаблон")).toBeInTheDocument();
  expect(await screen.findByText("50%")).toBeInTheDocument();
  expect(await screen.findByText("30%")).toBeInTheDocument();
  expect(await screen.findByText("20%")).toBeInTheDocument();
});

test("stats data quality renders low confidence items", async () => {
  configureApi();
  statsRoute();
  useDashboardFixture();

  render(<App />);

  expect(await screen.findByText("Качество данных")).toBeInTheDocument();
  expect(await screen.findByText("точная этикетка")).toBeInTheDocument();
  expect(await screen.findAllByText("оценка по фото")).not.toHaveLength(0);
  expect(await screen.findByText("Unclear plated meal")).toBeInTheDocument();
  expect(await screen.findByText("0.42")).toBeInTheDocument();
});

test("glucose page renders dashboard and sensor panel", async () => {
  configureApi();
  glucoseRoute();

  render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Глюкоза" }),
  ).toBeInTheDocument();
  expect(
    await screen.findByRole("img", { name: "График глюкозы" }),
  ).toBeInTheDocument();
  expect(await screen.findAllByText("Sensor A")).not.toHaveLength(0);
  expect(await screen.findByText(/Запись из пальца/)).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Эпизоды" })).toBeInTheDocument();
  expect(await screen.findByText("Приём пищи")).toBeInTheDocument();
});

test("glucose pull button imports current Nightscout data", async () => {
  configureApi();
  glucoseRoute();
  let importCount = 0;

  server.use(
    http.get("http://api.test/settings/nightscout", () =>
      HttpResponse.json({
        enabled: true,
        configured: true,
        connected: true,
        url: "https://nightscout.test",
        secret_is_set: true,
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
    http.post("http://api.test/nightscout/import", async ({ request }) => {
      importCount += 1;
      const body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        from_datetime: body.from_datetime,
        to_datetime: body.to_datetime,
        glucose_imported: 2,
        insulin_imported: 1,
        glucose_total: 2,
        insulin_total: 1,
        last_error: null,
      });
    }),
  );

  render(<App />);

  const button = await screen.findByRole("button", {
    name: "Подтянуть актуальные данные",
  });
  await waitFor(() => expect(button).toBeEnabled());
  await waitFor(() => expect(importCount).toBeGreaterThanOrEqual(1));
  const importsBeforeClick = importCount;
  await userEvent.click(button);

  await waitFor(() => expect(importCount).toBeGreaterThan(importsBeforeClick));
  expect(await screen.findByText(/Обновлено/)).toBeInTheDocument();
});

test("glucose defaults to normalized mode and exposes raw and smoothed modes", async () => {
  configureApi();
  glucoseRoute();
  const requestedModes: string[] = [];

  server.use(
    http.get("http://api.test/glucose/dashboard", ({ request }) => {
      const mode = new URL(request.url).searchParams.get("mode") ?? "raw";
      requestedModes.push(mode);
      return HttpResponse.json({
        from_datetime: "2026-04-28T04:00:00",
        to_datetime: "2026-04-28T10:00:00",
        mode,
        points: [
          {
            timestamp: "2026-04-28T08:00:00",
            raw_value: 6,
            smoothed_value: 6.1,
            normalized_value: 6.8,
            display_value: mode === "normalized" ? 6.8 : mode === "smoothed" ? 6.1 : 6,
            correction_mmol_l: 0.8,
            flags: [],
          },
          {
            timestamp: "2026-04-28T08:05:00",
            raw_value: 6.2,
            smoothed_value: 6.2,
            normalized_value: 7,
            display_value: mode === "normalized" ? 7 : 6.2,
            correction_mmol_l: 0.8,
            flags: [],
          },
        ],
        fingersticks: [],
        food_events: [],
        insulin_events: [],
        artifacts: [],
        current_sensor: null,
        sensors: [],
        quality: {
          sensor: null,
          sensor_age_days: null,
          sensor_phase: null,
          fingerstick_count: 0,
          valid_calibration_points: 0,
          matched_calibration_points: 0,
          stable_calibration_points: 0,
          warmup_calibration_points: 0,
          calibration_basis: "insufficient",
          warmup_metrics: null,
          median_bias_mmol_l: null,
          mad_mmol_l: null,
          mard_percent: null,
          drift_mmol_l_per_day: null,
          residual_mad_mmol_l: null,
          missing_data_pct: null,
          suspected_compression_count: 0,
          noise_score: 0,
          quality_score: 0,
          confidence: "none",
          notes: [],
          active_model: null,
        },
        summary: {
          current_glucose: mode === "normalized" ? 7 : 6.2,
          current_glucose_at: "2026-04-28T08:05:00",
          sensor_age_days: null,
          bias_mmol_l: null,
          drift_mmol_l_per_day: null,
          calibration_confidence: "none",
          suspected_compression_count: 0,
        },
        notes: [],
      });
    }),
  );

  render(<App />);

  await waitFor(() => expect(requestedModes[0]).toBe("normalized"));
  expect(
    screen.getByRole("button", { name: "Нормализованная" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Сглаженная" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Raw" }));

  await waitFor(() => expect(requestedModes).toContain("raw"));
  expect(await screen.findByText(/Смещение в этот момент \+0\.8/)).toBeInTheDocument();
  expect(screen.getByText("Raw CGM сохраняется без изменений")).toBeInTheDocument();
});

test("glucose fingerstick form posts manual reading", async () => {
  configureApi();
  glucoseRoute();
  const postedBody: { current: Record<string, unknown> | null } = {
    current: null,
  };

  server.use(
    http.post("http://api.test/fingersticks", async ({ request }) => {
      postedBody.current = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        {
          id: "fingerstick-created",
          created_at: "2026-04-28T10:00:00.000Z",
          ...postedBody.current,
        },
        { status: 201 },
      );
    }),
  );

  render(<App />);

  await screen.findByRole("heading", { name: "Глюкоза" });
  await userEvent.click(
    screen.getByRole("button", { name: "+ Запись из пальца" }),
  );
  fireEvent.change(screen.getByLabelText("глюкоза, ммоль/л"), {
    target: { value: "7.4" },
  });
  await userEvent.type(screen.getByLabelText("глюкометр"), "Contour");
  await userEvent.click(screen.getByRole("button", { name: "Добавить" }));

  await waitFor(() => expect(postedBody.current?.glucose_mmol_l).toBe(7.4));
  expect(postedBody.current?.meter_name).toBe("Contour");
});

test("glucose fingerstick rows can be edited", async () => {
  configureApi();
  glucoseRoute();
  const patched: {
    body: Record<string, unknown> | null;
    id: string | undefined;
  } = {
    body: null,
    id: undefined,
  };

  server.use(
    http.patch("http://api.test/fingersticks/:fingerstickId", async ({ params, request }) => {
      patched.id = String(params.fingerstickId);
      patched.body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        id: patched.id,
        created_at: "2026-04-28T10:00:00.000Z",
        notes: null,
        ...patched.body,
      });
    }),
  );

  render(<App />);

  await screen.findByRole("heading", { name: "Глюкоза" });
  await userEvent.click(await screen.findByRole("button", { name: "изменить" }));
  expect(
    await screen.findByText("Редактировать запись из пальца"),
  ).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("время"), {
    target: { value: "2026-04-28T21:45" },
  });
  fireEvent.change(screen.getByLabelText("глюкоза, ммоль/л"), {
    target: { value: "4.8" },
  });
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить изменения" }),
  );

  await waitFor(() => expect(patched.id).toBe("fingerstick-1"));
  expect(patched.body?.measured_at).toBe("2026-04-28T21:45:00");
  expect(patched.body?.glucose_mmol_l).toBe(4.8);
});
