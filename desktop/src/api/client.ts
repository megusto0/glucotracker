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
export type MealItemWeightReuseRequest =
  components["schemas"]["MealItemWeightReuseRequest"];
export type MealPageResponse = components["schemas"]["MealPageResponse"];
export type MealResponse = components["schemas"]["MealResponse"];
export type PhotoResponse = components["schemas"]["PhotoResponse"];
export type PatternResponse = components["schemas"]["PatternResponse"];
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
export type StatsInsightResponse =
  components["schemas"]["StatsInsightResponse"];
export type ScheduleResponse = components["schemas"]["ScheduleResponse"];
export type ScheduleOverrideRequest =
  components["schemas"]["ScheduleOverrideRequest"];
export type NonTypicalPeriodCreate =
  components["schemas"]["NonTypicalPeriodCreate"];
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
export type NightscoutLatestReadingResponse =
  components["schemas"]["NightscoutLatestReadingResponse"];
export type TimelineResponse = components["schemas"]["TimelineResponse"];
export type FoodEpisodeResponse =
  components["schemas"]["FoodEpisodeResponse"];
export type InsulinLinkDayPutRequest =
  components["schemas"]["InsulinLinkDayPutRequest"];
export type InsulinLinkDayResponse =
  components["schemas"]["InsulinLinkDayResponse"];
export type MealInsulinLinkItem =
  components["schemas"]["MealInsulinLinkItem"];
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
export type ReportGlucoseMode =
  NonNullable<EndocrinologistReportResponse["glucose_mode"]>;
export type GlucoseDashboardResponse =
  components["schemas"]["GlucoseDashboardResponse"];
export type GlucoseMode = GlucoseDashboardResponse["mode"];
export type FingerstickReadingCreate =
  components["schemas"]["FingerstickReadingCreate"];
export type FingerstickReadingPatch =
  components["schemas"]["FingerstickReadingPatch"];
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
export type UserProfileResponse = components["schemas"]["UserProfileResponse"];
export type UserProfileUpdate = components["schemas"]["UserProfileUpdate"];
export type ActivitySyncRequest = components["schemas"]["ActivitySyncRequest"];
export type ActivitySyncResponse = components["schemas"]["ActivitySyncResponse"];
export type KcalBalanceResponse = components["schemas"]["KcalBalanceResponse"];
export type KcalBalanceDay = components["schemas"]["KcalBalanceDay"];
export type KcalBalanceRangeResponse = components["schemas"]["KcalBalanceRangeResponse"];

export type ApiConfig = {
  baseUrl: string;
  token: string;
};

export type LoginRequest = {
  username: string;
  password: string;
};

export type RefreshRequest = {
  refresh_token: string;
};

export type LogoutRequest = RefreshRequest;

export type IssuedTokensResponse = {
  access: string;
  refresh: string;
  access_expires_at: string;
  refresh_expires_at: string;
};

export type CurrentUserDetailResponse = {
  id: string;
  username: string;
  role: "gluco" | "food";
  created_at: string;
  last_login_at?: string | null;
  features: string[];
  feature_flags: Record<string, unknown>;
};

type QueryValue = string | number | boolean | null | undefined;

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  query?: Record<string, QueryValue>;
  body?: unknown;
  auth?: boolean;
  formData?: FormData;
  timeoutMs?: number;
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

export class ApiTimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(`Backend не ответил за ${Math.round(timeoutMs / 1000)} с.`);
    this.name = "ApiTimeoutError";
    this.timeoutMs = timeoutMs;
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

const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

const isAbortError = (error: unknown) =>
  error instanceof Error && error.name === "AbortError";

const withRequestTimeout = async <T>(
  request: Promise<T>,
  timeoutMs?: number,
  controller?: AbortController,
) => {
  if (!timeoutMs) return request;

  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      controller?.abort();
      reject(new ApiTimeoutError(timeoutMs));
    }, timeoutMs);
  });

  try {
    return await Promise.race([request, timeout]);
  } catch (error) {
    if (isAbortError(error)) {
      throw new ApiTimeoutError(timeoutMs);
    }
    throw error;
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }
};

const normalizeBaseUrl = (baseUrl: string) => {
  const trimmed = baseUrl.trim().replace(/\/+$/, "");
  const url = new URL(
    trimmed || import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
  );
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

let _connectionManagerNotify: {
  onSuccess: () => void;
  onFailure: (error: string) => void;
} | null = null;

let _authSessionManager: {
  refreshAccessToken: () => Promise<string | null>;
  clearAuthSession: () => void;
} | null = null;

export function setConnectionNotifier(notifier: {
  onSuccess: () => void;
  onFailure: (error: string) => void;
} | null) {
  _connectionManagerNotify = notifier;
}

export function setAuthSessionManager(manager: {
  refreshAccessToken: () => Promise<string | null>;
  clearAuthSession: () => void;
} | null) {
  _authSessionManager = manager;
}

async function apiRequestOnce<T>(
  path: string,
  config: ApiConfig,
  options: RequestOptions = {},
  tokenOverride?: string,
): Promise<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
  const controller = new AbortController();
  const headers = new Headers();
  headers.set("X-Glucotracker-Client", "desktop");
  if (options.body !== undefined && !options.formData) {
    headers.set("Content-Type", "application/json");
  }
  const token = tokenOverride ?? config.token;
  if (options.auth !== false && token.trim()) {
    headers.set("Authorization", `Bearer ${token.trim()}`);
  }

  const response = await withRequestTimeout(
    runtimeFetch(buildUrl(config.baseUrl, path, options.query), {
      method: options.method ?? "GET",
      headers,
      signal: controller.signal,
      body: options.formData
        ? options.formData
        : options.body === undefined
          ? undefined
          : JSON.stringify(options.body),
    }),
    timeoutMs,
    controller,
  );

  return parseResponse<T>(response);
}

export async function apiRequest<T>(
  path: string,
  config: ApiConfig,
  options: RequestOptions = {},
): Promise<T> {
  try {
    const result = await apiRequestOnce<T>(path, config, options);
    if (_connectionManagerNotify && path !== "/health") {
      _connectionManagerNotify.onSuccess();
    }
    return result;
  } catch (error: unknown) {
    if (
      options.auth !== false &&
      error instanceof ApiError &&
      error.status === 401 &&
      _authSessionManager
    ) {
      const refreshedToken = await _authSessionManager.refreshAccessToken();
      if (refreshedToken) {
        const result = await apiRequestOnce<T>(
          path,
          config,
          options,
          refreshedToken,
        );
        if (_connectionManagerNotify && path !== "/health") {
          _connectionManagerNotify.onSuccess();
        }
        return result;
      }
      _authSessionManager.clearAuthSession();
    }

    if (_connectionManagerNotify && path !== "/health") {
      const message = error instanceof Error ? error.message : String(error);
      if (
        error instanceof ApiError &&
        (error.status === 401 || error.status === 403 || error.status === 404)
      ) {
        // do not report auth/not-found as connection failures
      } else {
        _connectionManagerNotify.onFailure(message);
      }
    }
    throw error;
  }
}

async function apiBlobRequest(
  path: string,
  config: ApiConfig,
  options: RequestOptions = {},
  tokenOverride?: string,
): Promise<Blob> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
  const controller = new AbortController();
  const headers = new Headers();
  headers.set("X-Glucotracker-Client", "desktop");
  const token = tokenOverride ?? config.token;
  if (options.auth !== false && token.trim()) {
    headers.set("Authorization", `Bearer ${token.trim()}`);
  }

  try {
    let response = await withRequestTimeout(
      runtimeFetch(buildUrl(config.baseUrl, path, options.query), {
        method: options.method ?? "GET",
        headers,
        signal: controller.signal,
      }),
      timeoutMs,
      controller,
    );

    if (
      options.auth !== false &&
      response.status === 401 &&
      _authSessionManager
    ) {
      const refreshedToken = await _authSessionManager.refreshAccessToken();
      if (refreshedToken) {
        return apiBlobRequest(path, config, options, refreshedToken);
      }
      _authSessionManager.clearAuthSession();
    }

    if (!response.ok) {
      const contentType = response.headers.get("content-type") ?? "";
      const detail = contentType.includes("application/json")
        ? await response.json()
        : await response.text();
      throw new ApiError(response.status, detail);
    }

    const bytes = await response.arrayBuffer();
    const blob = new Blob([bytes], {
      type: response.headers.get("content-type") ?? "application/octet-stream",
    });

    if (_connectionManagerNotify) {
      _connectionManagerNotify.onSuccess();
    }
    return blob;
  } catch (error: unknown) {
    if (_connectionManagerNotify) {
      const message = error instanceof Error ? error.message : String(error);
      if (
        error instanceof ApiError &&
        (error.status === 401 || error.status === 403 || error.status === 404)
      ) {
        // auth errors are not connection failures
      } else {
        _connectionManagerNotify.onFailure(message);
      }
    }
    throw error;
  }
}

export const apiClient = {
  login: (config: ApiConfig, body: LoginRequest) =>
    apiRequest<IssuedTokensResponse>("/auth/login", config, {
      auth: false,
      method: "POST",
      body,
    }),

  refreshAuthToken: (config: ApiConfig, body: RefreshRequest) =>
    apiRequest<IssuedTokensResponse>("/auth/refresh", config, {
      auth: false,
      method: "POST",
      body,
    }),

  logout: (config: ApiConfig, body: LogoutRequest) =>
    apiRequest<void>("/auth/logout", config, {
      auth: false,
      method: "POST",
      body,
    }),

  me: (config: ApiConfig) =>
    apiRequest<CurrentUserDetailResponse>("/auth/me", config),

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
      sweet?: boolean;
      breakfast?: boolean;
      photo_only?: boolean;
      low_confidence?: boolean;
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

  createMealFromItemWeight: (
    config: ApiConfig,
    itemId: string,
    body: MealItemWeightReuseRequest,
  ) =>
    apiRequest<MealResponse>(
      `/meal_items/${itemId}/copy_by_weight`,
      config,
      {
        method: "POST",
        body,
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

  uploadPatternImage: (config: ApiConfig, patternId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiRequest<PatternResponse>(`/patterns/${patternId}/image`, config, {
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

  getStatsInsights: (
    config: ApiConfig,
    period: "7d" | "14d" | "30d" = "14d",
    slot: "stats" | "today" = "stats",
  ) =>
    apiRequest<{ insights: StatsInsightResponse[] }>("/stats/insights", config, {
      query: { period, slot },
    }),

  getSchedule: (config: ApiConfig) =>
    apiRequest<ScheduleResponse>("/me/schedule", config),

  putScheduleOverride: (config: ApiConfig, body: ScheduleOverrideRequest) =>
    apiRequest<ScheduleResponse>("/me/schedule/override", config, {
      method: "PUT",
      body,
    }),

  deleteScheduleOverride: (config: ApiConfig) =>
    apiRequest<ScheduleResponse>("/me/schedule/override", config, {
      method: "DELETE",
    }),

  createNonTypicalPeriod: (config: ApiConfig, body: NonTypicalPeriodCreate) =>
    apiRequest<NonNullable<ScheduleResponse["non_typical_periods"]>[number]>(
      "/me/schedule/non-typical-periods",
      config,
      {
        method: "POST",
        body,
      },
    ),

  deleteNonTypicalPeriod: (config: ApiConfig, periodId: string) =>
    apiRequest<{ deleted: boolean }>(
      `/me/schedule/non-typical-periods/${periodId}`,
      config,
      {
        method: "DELETE",
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
      timeoutMs: 60_000,
    }),

  getNightscoutLatestReading: (config: ApiConfig) =>
    apiRequest<NightscoutLatestReadingResponse>(
      "/nightscout/latest-reading",
      config,
    ),

  getTimeline: (config: ApiConfig, from: string, to: string) =>
    apiRequest<TimelineResponse>("/timeline", config, {
      query: { from, to },
    }),

  getTimelineInsulinLinks: (config: ApiConfig, date: string) =>
    apiRequest<InsulinLinkDayResponse>("/timeline/insulin-links", config, {
      query: { date },
    }),

  putTimelineInsulinLinks: (
    config: ApiConfig,
    body: InsulinLinkDayPutRequest,
  ) =>
    apiRequest<InsulinLinkDayResponse>("/timeline/insulin-links", config, {
      method: "PUT",
      body,
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

  patchFingerstick: (
    config: ApiConfig,
    fingerstickId: string,
    body: FingerstickReadingPatch,
  ) =>
    apiRequest<FingerstickReadingResponse>(
      `/fingersticks/${fingerstickId}`,
      config,
      {
        method: "PATCH",
        body,
      },
    ),

  deleteFingerstick: (config: ApiConfig, fingerstickId: string) =>
    apiRequest<void>(`/fingersticks/${fingerstickId}`, config, {
      method: "DELETE",
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

  getEndocrinologistReport: (
    config: ApiConfig,
    from: string,
    to: string,
    glucoseMode: ReportGlucoseMode = "raw",
  ) =>
    apiRequest<EndocrinologistReportResponse>(
      "/reports/endocrinologist",
      config,
      { query: { from, to, glucose_mode: glucoseMode } },
    ),

  adminRecalculate: (config: ApiConfig, from: string, to: string) =>
    apiRequest<AdminRecalculateResponse>("/admin/recalculate", config, {
      method: "POST",
      query: { from, to },
    }),

  getUserProfile: (config: ApiConfig) =>
    apiRequest<UserProfileResponse>("/profile", config),

  updateUserProfile: (config: ApiConfig, body: UserProfileUpdate) =>
    apiRequest<UserProfileResponse>("/profile", config, {
      method: "PUT",
      body,
    }),

  syncActivity: (config: ApiConfig, body: ActivitySyncRequest) =>
    apiRequest<ActivitySyncResponse>("/activity/sync", config, {
      method: "POST",
      body,
    }),

  getKcalBalance: (config: ApiConfig, day: string) =>
    apiRequest<KcalBalanceResponse>("/activity/balance", config, {
      query: { day },
    }),

  getKcalBalanceRange: (config: ApiConfig, from: string, to: string) =>
    apiRequest<KcalBalanceRangeResponse>("/activity/balance/range", config, {
      query: { from_date: from, to_date: to },
    }),
};
