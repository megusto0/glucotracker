import { isTauri } from "@tauri-apps/api/core";
import { fetch as tauriFetch } from "@tauri-apps/plugin-http";
import type { components } from "./generated/schema";

export type AutocompleteSuggestion =
  components["schemas"]["AutocompleteSuggestion"];
export type EstimateMealRequest = components["schemas"]["EstimateMealRequest"];
export type EstimateMealResponse =
  components["schemas"]["EstimateMealResponse"];
export type EstimateCreatedDraftResponse =
  components["schemas"]["EstimateCreatedDraftResponse"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type MealCreate = components["schemas"]["MealCreate"];
export type MealPatch = components["schemas"]["MealPatch"];
export type MealItemCreate = components["schemas"]["MealItemCreate"];
export type MealItemPatch = components["schemas"]["MealItemPatch"];
export type MealItemResponse = components["schemas"]["MealItemResponse"];
export type MealPageResponse = components["schemas"]["MealPageResponse"];
export type MealResponse = components["schemas"]["MealResponse"];
export type PhotoResponse = components["schemas"]["PhotoResponse"];
export type ProductResponse = components["schemas"]["ProductResponse"];
export type ProductCreate = components["schemas"]["ProductCreate"];
export type ProductPatch = components["schemas"]["ProductPatch"];
export type DashboardTodayResponse =
  components["schemas"]["DashboardTodayResponse"];
export type DashboardRangeResponse =
  components["schemas"]["DashboardRangeResponse"];
export type DashboardDayResponse =
  components["schemas"]["DashboardDayResponse"];
export type DashboardHeatmapResponse =
  components["schemas"]["DashboardHeatmapResponse"];
export type DashboardTopPatternResponse =
  components["schemas"]["DashboardTopPatternResponse"];
export type DashboardSourceBreakdownResponse =
  components["schemas"]["DashboardSourceBreakdownResponse"];
export type DashboardDataQualityResponse =
  components["schemas"]["DashboardDataQualityResponse"];
export type NightscoutStatusResponse =
  components["schemas"]["NightscoutStatusResponse"];
export type NightscoutSettingsPatch =
  components["schemas"]["NightscoutSettingsPatch"];
export type NightscoutSettingsResponse =
  components["schemas"]["NightscoutSettingsResponse"];
export type NightscoutTestResponse =
  components["schemas"]["NightscoutTestResponse"];
export type NightscoutDayStatusResponse =
  components["schemas"]["NightscoutDayStatusResponse"];
export type NightscoutSyncResponse =
  components["schemas"]["NightscoutSyncResponse"];
export type NightscoutSyncTodayResponse =
  components["schemas"]["NightscoutSyncTodayResponse"];
export type NightscoutEventsResponse =
  components["schemas"]["NightscoutEventsResponse"];
export type NightscoutImportRequest =
  components["schemas"]["NightscoutImportRequest"];
export type NightscoutImportResponse =
  components["schemas"]["NightscoutImportResponse"];
export type TimelineResponse = components["schemas"]["TimelineResponse"];
export type FoodEpisodeResponse =
  components["schemas"]["FoodEpisodeResponse"];
export type AdminRecalculateResponse =
  components["schemas"]["AdminRecalculateResponse"];
export type DatabaseItemResponse =
  components["schemas"]["DatabaseItemResponse"];
export type DatabaseItemPageResponse =
  components["schemas"]["DatabaseItemPageResponse"];
export type AIRunResponse = components["schemas"]["AIRunResponse"];
export type ReestimateMealRequest =
  components["schemas"]["ReestimateMealRequest"];
export type ReestimateMealResponse =
  components["schemas"]["ReestimateMealResponse"];
export type ApplyEstimationRunRequest =
  components["schemas"]["ApplyEstimationRunRequest"];
export type ApplyEstimationRunResponse =
  components["schemas"]["ApplyEstimationRunResponse"];
export type EndocrinologistReportResponse =
  components["schemas"]["EndocrinologistReportResponse"];
export type GlucoseDashboardResponse =
  components["schemas"]["GlucoseDashboardResponse"];
export type GlucoseMode = GlucoseDashboardResponse["mode"];
export type FingerstickReadingCreate =
  components["schemas"]["FingerstickReadingCreate"];
export type FingerstickReadingResponse =
  components["schemas"]["FingerstickReadingResponse"];
export type SensorSessionCreate =
  components["schemas"]["SensorSessionCreate"];
export type SensorSessionPatch =
  components["schemas"]["SensorSessionPatch"];
export type SensorSessionResponse =
  components["schemas"]["SensorSessionResponse"];
export type SensorQualityResponse =
  components["schemas"]["SensorQualityResponse"];
export type CgmCalibrationModelResponse =
  components["schemas"]["CgmCalibrationModelResponse"];

export type ApiConfig = {
  baseUrl: string;
  token: string;
};

type QueryValue = string | number | boolean | null | undefined;

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  query?: Record<string, QueryValue>;
  body?: unknown;
  auth?: boolean;
  formData?: FormData;
};

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(`API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function apiErrorMessage(
  error: unknown,
  fallback = "Запрос не выполнен.",
) {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string" && error.detail.trim()) {
      return error.detail;
    }
    if (
      error.detail &&
      typeof error.detail === "object" &&
      "detail" in error.detail
    ) {
      const detail = (error.detail as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) {
        return detail;
      }
    }
    return `Backend вернул HTTP ${error.status}.`;
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return fallback;
}

export const apiRuntimeName = () =>
  isTauri() ||
  (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window)
    ? "tauri-http"
    : "browser-fetch";

const runtimeFetch = (url: string, init: RequestInit) => {
  if (apiRuntimeName() === "tauri-http") {
    return tauriFetch(url, init);
  }
  return fetch(url, init);
};

const normalizeBaseUrl = (baseUrl: string) => {
  const trimmed = baseUrl.trim().replace(/\/+$/, "");
  const url = new URL(trimmed || "http://127.0.0.1:8000");
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("Backend URL must use http or https.");
  }
  return url.toString().replace(/\/+$/, "");
};

const buildUrl = (
  baseUrl: string,
  path: string,
  query?: Record<string, QueryValue>,
) => {
  const url = new URL(`${normalizeBaseUrl(baseUrl)}${path}`);
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return url.toString();
};

const parseResponse = async <T>(response: Response): Promise<T> => {
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    throw new ApiError(response.status, payload);
  }

  return payload as T;
};

export async function apiRequest<T>(
  path: string,
  config: ApiConfig,
  options: RequestOptions = {},
): Promise<T> {
  const headers = new Headers();
  if (options.body !== undefined && !options.formData) {
    headers.set("Content-Type", "application/json");
  }
  if (options.auth !== false && config.token.trim()) {
    headers.set("Authorization", `Bearer ${config.token.trim()}`);
  }

  const response = await runtimeFetch(
    buildUrl(config.baseUrl, path, options.query),
    {
      method: options.method ?? "GET",
      headers,
      body: options.formData
        ? options.formData
        : options.body === undefined
          ? undefined
          : JSON.stringify(options.body),
    },
  );

  return parseResponse<T>(response);
}

async function apiBlobRequest(
  path: string,
  config: ApiConfig,
  options: RequestOptions = {},
): Promise<Blob> {
  const headers = new Headers();
  if (options.auth !== false && config.token.trim()) {
    headers.set("Authorization", `Bearer ${config.token.trim()}`);
  }

  const response = await runtimeFetch(
    buildUrl(config.baseUrl, path, options.query),
    {
      method: options.method ?? "GET",
      headers,
    },
  );

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    const detail = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    throw new ApiError(response.status, detail);
  }

  const bytes = await response.arrayBuffer();
  return new Blob([bytes], {
    type: response.headers.get("content-type") ?? "application/octet-stream",
  });
}

export const apiClient = {
  health: (config: ApiConfig) =>
    apiRequest<HealthResponse>("/health", config, { auth: false }),

  openapi: (config: ApiConfig) =>
    apiRequest<Record<string, unknown>>("/openapi.json", config, {
      auth: false,
    }),

  listMeals: (
    config: ApiConfig,
    query: {
      limit?: number;
      offset?: number;
      q?: string;
      status?: string;
      from?: string;
      to?: string;
    } = {},
  ) => apiRequest<MealPageResponse>("/meals", config, { query }),

  createMeal: (config: ApiConfig, body: MealCreate) =>
    apiRequest<MealResponse>("/meals", config, { method: "POST", body }),

  getMeal: (config: ApiConfig, mealId: string) =>
    apiRequest<MealResponse>(`/meals/${mealId}`, config),

  updateMeal: (config: ApiConfig, mealId: string, body: MealPatch) =>
    apiRequest<MealResponse>(`/meals/${mealId}`, config, {
      method: "PATCH",
      body,
    }),

  deleteMeal: (config: ApiConfig, mealId: string) =>
    apiRequest<{ deleted: boolean }>(`/meals/${mealId}`, config, {
      method: "DELETE",
    }),

  autocomplete: (config: ApiConfig, q: string, limit = 20) =>
    apiRequest<AutocompleteSuggestion[]>("/autocomplete", config, {
      query: { q, limit },
    }),

  listDatabaseItems: (
    config: ApiConfig,
    query: {
      limit?: number;
      offset?: number;
      q?: string;
      source?: string;
      type?: string;
      needs_review?: boolean;
    } = {},
  ) =>
    apiRequest<DatabaseItemPageResponse>("/database/items", config, { query }),

  replaceMealItems: (
    config: ApiConfig,
    mealId: string,
    items: MealItemCreate[],
  ) =>
    apiRequest<MealResponse>(`/meals/${mealId}/items`, config, {
      method: "PUT",
      body: items,
    }),

  updateMealItem: (config: ApiConfig, itemId: string, body: MealItemPatch) =>
    apiRequest<MealItemResponse>(`/meal_items/${itemId}`, config, {
      method: "PATCH",
      body,
    }),

  rememberProductFromMealItem: (
    config: ApiConfig,
    itemId: string,
    aliases: string[] = [],
  ) =>
    apiRequest<ProductResponse>(
      `/meal_items/${itemId}/remember_product`,
      config,
      {
        method: "POST",
        body: { aliases },
      },
    ),

  createProduct: (config: ApiConfig, body: ProductCreate) =>
    apiRequest<ProductResponse>("/products", config, {
      method: "POST",
      body,
    }),

  updateProduct: (config: ApiConfig, productId: string, body: ProductPatch) =>
    apiRequest<ProductResponse>(`/products/${productId}`, config, {
      method: "PATCH",
      body,
    }),

  uploadProductImage: (config: ApiConfig, productId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiRequest<ProductResponse>(`/products/${productId}/image`, config, {
      method: "POST",
      formData,
    });
  },

  uploadMealPhoto: (config: ApiConfig, mealId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiRequest<PhotoResponse>(`/meals/${mealId}/photos`, config, {
      method: "POST",
      formData,
    });
  },

  getPhotoFile: (config: ApiConfig, photoId: string) =>
    apiBlobRequest(`/photos/${photoId}/file`, config),

  getImageFile: (config: ApiConfig, path: string) =>
    apiBlobRequest(path.startsWith("/") ? path : `/${path}`, config),

  estimateAndSaveDraft: (
    config: ApiConfig,
    mealId: string,
    body: EstimateMealRequest = { model: "default" },
  ) =>
    apiRequest<EstimateMealResponse>(
      `/meals/${mealId}/estimate_and_save_draft`,
      config,
      {
        method: "POST",
        body,
      },
    ),

  reestimateMeal: (
    config: ApiConfig,
    mealId: string,
    body: ReestimateMealRequest,
  ) =>
    apiRequest<ReestimateMealResponse>(`/meals/${mealId}/reestimate`, config, {
      method: "POST",
      body,
    }),

  applyEstimationRun: (
    config: ApiConfig,
    mealId: string,
    runId: string,
    body: ApplyEstimationRunRequest,
  ) =>
    apiRequest<ApplyEstimationRunResponse>(
      `/meals/${mealId}/apply_estimation_run/${runId}`,
      config,
      {
        method: "POST",
        body,
      },
    ),

  listMealAiRuns: (config: ApiConfig, mealId: string) =>
    apiRequest<AIRunResponse[]>(`/meals/${mealId}/ai_runs`, config),

  acceptMeal: (config: ApiConfig, mealId: string, items: MealItemCreate[]) =>
    apiRequest<MealResponse>(`/meals/${mealId}/accept`, config, {
      method: "POST",
      body: { items },
    }),

  discardMeal: (config: ApiConfig, mealId: string) =>
    apiRequest<MealResponse>(`/meals/${mealId}/discard`, config, {
      method: "POST",
    }),

  getDashboardToday: (config: ApiConfig) =>
    apiRequest<DashboardTodayResponse>("/dashboard/today", config),

  getDashboardRange: (config: ApiConfig, from: string, to: string) =>
    apiRequest<DashboardRangeResponse>("/dashboard/range", config, {
      query: { from, to },
    }),

  getDashboardHeatmap: (config: ApiConfig, weeks = 4) =>
    apiRequest<DashboardHeatmapResponse>("/dashboard/heatmap", config, {
      query: { weeks },
    }),

  getDashboardTopPatterns: (config: ApiConfig, days = 7, limit = 10) =>
    apiRequest<DashboardTopPatternResponse[]>(
      "/dashboard/top_patterns",
      config,
      {
        query: { days, limit },
      },
    ),

  getDashboardSourceBreakdown: (config: ApiConfig, days = 7) =>
    apiRequest<DashboardSourceBreakdownResponse>(
      "/dashboard/source_breakdown",
      config,
      {
        query: { days },
      },
    ),

  getDashboardDataQuality: (config: ApiConfig, days = 7) =>
    apiRequest<DashboardDataQualityResponse>(
      "/dashboard/data_quality",
      config,
      {
        query: { days },
      },
    ),

  getNightscoutStatus: (config: ApiConfig) =>
    apiRequest<NightscoutStatusResponse>("/nightscout/status", config),

  getNightscoutSettings: (config: ApiConfig) =>
    apiRequest<NightscoutSettingsResponse>("/settings/nightscout", config),

  updateNightscoutSettings: (
    config: ApiConfig,
    body: NightscoutSettingsPatch,
  ) =>
    apiRequest<NightscoutSettingsResponse>("/settings/nightscout", config, {
      method: "PUT",
      body,
    }),

  testNightscoutConnection: (config: ApiConfig) =>
    apiRequest<NightscoutTestResponse>("/settings/nightscout/test", config, {
      method: "POST",
    }),

  getNightscoutDayStatus: (config: ApiConfig, date: string) =>
    apiRequest<NightscoutDayStatusResponse>("/nightscout/day_status", config, {
      query: { date },
    }),

  syncTodayToNightscout: (config: ApiConfig, date: string) =>
    apiRequest<NightscoutSyncTodayResponse>("/nightscout/sync/today", config, {
      method: "POST",
      body: { date, confirm: true },
    }),

  syncMealToNightscout: (config: ApiConfig, mealId: string) =>
    apiRequest<NightscoutSyncResponse>(
      `/meals/${mealId}/sync_nightscout`,
      config,
      { method: "POST" },
    ),

  unsyncMealFromNightscout: (config: ApiConfig, mealId: string) =>
    apiRequest<NightscoutSyncResponse>(
      `/meals/${mealId}/unsync_nightscout`,
      config,
      { method: "POST" },
    ),

  getNightscoutEvents: (config: ApiConfig, from: string, to: string) =>
    apiRequest<NightscoutEventsResponse>("/nightscout/events", config, {
      query: { from, to },
    }),

  importNightscoutContext: (
    config: ApiConfig,
    body: NightscoutImportRequest,
  ) =>
    apiRequest<NightscoutImportResponse>("/nightscout/import", config, {
      method: "POST",
      body,
    }),

  getTimeline: (config: ApiConfig, from: string, to: string) =>
    apiRequest<TimelineResponse>("/timeline", config, {
      query: { from, to },
    }),

  getGlucoseDashboard: (
    config: ApiConfig,
    from: string,
    to: string,
    mode: GlucoseMode = "raw",
  ) =>
    apiRequest<GlucoseDashboardResponse>("/glucose/dashboard", config, {
      query: { from, to, mode },
    }),

  listFingersticks: (
    config: ApiConfig,
    query: { from?: string; to?: string } = {},
  ) => apiRequest<FingerstickReadingResponse[]>("/fingersticks", config, { query }),

  createFingerstick: (config: ApiConfig, body: FingerstickReadingCreate) =>
    apiRequest<FingerstickReadingResponse>("/fingersticks", config, {
      method: "POST",
      body,
    }),

  listSensors: (config: ApiConfig) =>
    apiRequest<SensorSessionResponse[]>("/sensors", config),

  createSensor: (config: ApiConfig, body: SensorSessionCreate) =>
    apiRequest<SensorSessionResponse>("/sensors", config, {
      method: "POST",
      body,
    }),

  patchSensor: (config: ApiConfig, sensorId: string, body: SensorSessionPatch) =>
    apiRequest<SensorSessionResponse>(`/sensors/${sensorId}`, config, {
      method: "PATCH",
      body,
    }),

  getSensorQuality: (config: ApiConfig, sensorId: string) =>
    apiRequest<SensorQualityResponse>(`/sensors/${sensorId}/quality`, config),

  recalculateSensorCalibration: (config: ApiConfig, sensorId: string) =>
    apiRequest<CgmCalibrationModelResponse>(
      `/sensors/${sensorId}/recalculate-calibration`,
      config,
      { method: "POST" },
    ),

  getEndocrinologistReport: (config: ApiConfig, from: string, to: string) =>
    apiRequest<EndocrinologistReportResponse>(
      "/reports/endocrinologist",
      config,
      { query: { from, to } },
    ),

  adminRecalculate: (config: ApiConfig, from: string, to: string) =>
    apiRequest<AdminRecalculateResponse>("/admin/recalculate", config, {
      method: "POST",
      query: { from, to },
    }),
};
