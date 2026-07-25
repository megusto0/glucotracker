import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type {
  GlucoseDashboardResponse,
  GlucoseMode,
  GlucosePredictionMode,
  GlucosePredictionResponse,
} from "../../api/client";
import {
  useCreateNightscoutInsulin,
  useGlucoseDashboard,
  useGlucoseEpisodes,
  useGlucosePrediction,
  useInsulinRecommendation,
} from "../glucose/useGlucoseDashboard";
import { NightscoutPage } from "./NightscoutPage";

vi.mock("../glucose/useGlucoseDashboard", () => ({
  useCreateNightscoutInsulin: vi.fn(),
  useGlucoseDashboard: vi.fn(),
  useGlucoseEpisodes: vi.fn(),
  useGlucosePrediction: vi.fn(),
  useInsulinRecommendation: vi.fn(),
}));

const mockedUseDashboard = vi.mocked(useGlucoseDashboard);
const mockedUseEpisodes = vi.mocked(useGlucoseEpisodes);
const mockedUsePrediction = vi.mocked(useGlucosePrediction);
const mockedUseRecommendation = vi.mocked(useInsulinRecommendation);
const mockedUseCreateInsulin = vi.mocked(useCreateNightscoutInsulin);
const createInsulin = vi.fn();

function dashboard(mode: GlucoseMode): GlucoseDashboardResponse {
  const normalized = mode === "normalized";
  return {
    artifacts: [],
    current_sensor: null,
    fingersticks: [],
    food_events: [
      {
        carbs_g: 42,
        kcal: 510,
        meal_id: "11111111-1111-1111-1111-111111111111",
        timestamp: "2026-07-12T06:55:00Z",
        title: "Завтрак",
      },
    ],
    from_datetime: "2026-07-12T04:00:00Z",
    insulin_events: [
      {
        event_type: "Meal Bolus",
        insulin_units: 3.5,
        notes: null,
        timestamp: "2026-07-12T07:00:00Z",
      },
    ],
    mode,
    notes: [],
    points: [
      {
        display_value: normalized ? 6 : 5.3,
        flags: [],
        normalized_value: 6,
        raw_value: 5.3,
        smoothed_value: 5.4,
        timestamp: "2026-07-12T06:55:00Z",
      },
      {
        display_value: normalized ? 6.2 : 5.5,
        flags: [],
        normalized_value: 6.2,
        raw_value: 5.5,
        smoothed_value: 5.6,
        timestamp: "2026-07-12T07:00:00Z",
      },
    ],
    quality: {
      active_model: null,
      confidence: "high",
      fingerstick_count: 4,
      matched_calibration_points: 4,
      missing_data_pct: 5,
      noise_score: 3,
      notes: [],
      quality_score: 86,
      suspected_compression_count: 0,
      stable_calibration_points: 4,
      valid_calibration_points: 4,
      warmup_calibration_points: 0,
    },
    sensors: [],
    summary: {
      bias_mmol_l: 0.7,
      calibration_confidence: "high",
      cob_g: 21,
      cob_minutes_remaining: 90,
      cob_model_confidence: "none",
      cob_model_source: "macro_prior",
      current_glucose: normalized ? 6.2 : 5.5,
      current_glucose_at: "2026-07-12T07:00:00Z",
      drift_mmol_l_per_day: 0,
      iob_minutes_remaining: 120,
      iob_model_confidence: "none",
      iob_model_source: "population",
      iob_units: 1.75,
      sensor_age_days: 4,
      suspected_compression_count: 0,
    },
    to_datetime: "2026-07-12T07:00:00Z",
  };
}

function prediction(mode: GlucosePredictionMode): GlucosePredictionResponse {
  return {
    anchor_timestamp: "2026-07-12T07:00:00Z",
    anchor_value: mode === "normalized" ? 6.2 : 5.5,
    raw_anchor_value: 5.5,
    generated_at: "2026-07-12T07:01:00Z",
    horizon_minutes: 90,
    inputs: {
      active_kcal_3h: 130,
      asleep: false,
      carb_absorption_next_30m_g: 8.4,
      carbs_g_4h: 42,
      cob_remaining_g: 21,
      exercise_minutes_3h: 45,
      heart_rate_bpm: 92,
      insulin_units_5h: 3.5,
      insulin_action_next_30m_units: 0.24,
      iob_remaining_units: 1.75,
      resting_heart_rate_bpm: 58,
      sleep_hours_24h: 7.4,
    },
    mode,
    model: {
      algorithm: "known_input_kinetic_shape_ensemble",
      baseline_mae_mmol: 1.7,
      confidence: "medium",
      day_count: 30,
      sample_count: 1600,
      forecast_assumption: "no_new_food_or_insulin",
      validation_mae_mmol: 1.45,
      validation_post_meal_count: 320,
      validation_high_count: 20,
      validation_low_count: 40,
      version: "personal_known_input_shape_scenario_v4",
    },
    notes: ["Исследовательский прогноз."],
    points: Array.from({ length: 18 }, (_, index) => {
      const horizon = (index + 1) * 5;
      const value = (mode === "normalized" ? 6.2 : 5.5) + index * 0.08;
      return {
        band: index === 17 ? "high" : "in_range",
        ci_high: value + 1.2,
        ci_low: value - 1.2,
        confidence: 0.64 - index * 0.01,
        display_value: value,
        horizon_minutes: horizon,
        normalized_value: mode === "normalized" ? value : null,
        raw_ci_high: value + 1.2,
        raw_ci_low: value - 1.2,
        raw_value: value,
        timestamp: new Date(
          Date.parse("2026-07-12T07:00:00Z") + horizon * 60_000,
        ).toISOString(),
      };
    }),
    step_minutes: 5,
  };
}

describe("NightscoutPage", () => {
  beforeEach(() => {
    mockedUseDashboard.mockImplementation(
      (_from, _to, mode) =>
        ({
          data: dashboard(mode),
          error: null,
          isLoading: false,
        }) as ReturnType<typeof useGlucoseDashboard>,
    );
    mockedUsePrediction.mockImplementation(
      (mode) =>
        ({
          data: prediction(mode),
          error: null,
          isLoading: false,
        }) as ReturnType<typeof useGlucosePrediction>,
    );
    mockedUseEpisodes.mockReturnValue({
      data: {
        from_datetime: "2026-07-12T04:00:00Z",
        to_datetime: "2026-07-12T07:00:00Z",
        episodes: [
          {
            end_at: "2026-07-12T07:00:00Z",
            insulin: [],
            key: "breakfast",
            kind: "food_only",
            meal_ids: ["11111111-1111-1111-1111-111111111111"],
            start_at: "2026-07-12T06:55:00Z",
            total_carbs_g: 42,
            total_insulin_units: 0,
            total_kcal: 510,
          },
        ],
      },
      error: null,
      isLoading: false,
    } as unknown as ReturnType<typeof useGlucoseEpisodes>);
    mockedUseRecommendation.mockReturnValue({
      data: {
        confidence: "medium",
        correction_status: "target_required",
        matched_episode_count: 5,
        matches: [],
        meal_ids: ["11111111-1111-1111-1111-111111111111"],
        method_version: "historical-episode-median-v1",
        range_high_units: 4.3,
        range_low_units: 3.8,
        recommended_units: 4.1,
        status: "ready",
        target_carbs_g: 42,
        target_kcal: 510,
      },
      error: null,
      isError: false,
      isLoading: false,
    } as unknown as ReturnType<typeof useInsulinRecommendation>);
    createInsulin.mockReset();
    mockedUseCreateInsulin.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: false,
      mutateAsync: createInsulin,
    } as unknown as ReturnType<typeof useCreateNightscoutInsulin>);
  });

  test("switches between standard and normalized dashboard series", () => {
    const { container } = render(
      <MemoryRouter>
        <NightscoutPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("5.5")).toBeInTheDocument();
    expect(container.querySelectorAll(".ns-point--normalized")).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Нормализованный" }));

    expect(
      screen.getByRole("button", { name: "Нормализованный" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("6.2")).toBeInTheDocument();
    expect(
      container.querySelectorAll(".ns-point--normalized").length,
    ).toBeGreaterThan(0);
    expect(mockedUseDashboard).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      "normalized",
    );
  });

  test("shows on-board status and anchors treatments around normalized points", () => {
    mockedUseDashboard.mockImplementation((_from, _to, mode) => {
      const data = dashboard(mode);
      return {
        data: {
          ...data,
          insulin_events: data.insulin_events.map((event) => ({
            ...event,
            timestamp: data.food_events[0]!.timestamp,
          })),
        },
        error: null,
        isLoading: false,
      } as ReturnType<typeof useGlucoseDashboard>;
    });
    const { container } = render(
      <MemoryRouter>
        <NightscoutPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("IOB")).toBeInTheDocument();
    expect(screen.getByText("1.75")).toBeInTheDocument();
    expect(screen.getByText("120 мин до завершения")).toBeInTheDocument();
    expect(screen.getByText("COB")).toBeInTheDocument();
    expect(screen.getByText("21.0")).toBeInTheDocument();
    expect(screen.getByText("90 мин до усвоения")).toBeInTheDocument();
    expect(container.querySelectorAll(".ns-treatment--food")).toHaveLength(1);
    expect(container.querySelectorAll(".ns-treatment--insulin")).toHaveLength(
      1,
    );

    fireEvent.click(screen.getByRole("button", { name: "Нормализованный" }));

    // Same CGM anchor: insulin is above it, carbs are below it.
    const glucosePoint = container.querySelector(".ns-point--normalized");
    const foodMarker = container.querySelector(".ns-treatment--food");
    const insulinMarker = container.querySelector(".ns-treatment--insulin");
    const anchorX = glucosePoint?.getAttribute("cx");
    const anchorY = Number(glucosePoint?.getAttribute("cy"));
    const foodTransform = foodMarker?.getAttribute("transform") ?? "";
    const insulinTransform = insulinMarker?.getAttribute("transform") ?? "";
    expect(foodTransform).toMatch(new RegExp(`^translate\\(${anchorX} `));
    expect(insulinTransform).toMatch(new RegExp(`^translate\\(${anchorX} `));
    const foodY = Number(
      foodTransform.match(/translate\([^ ]+ ([^)]+)\)/)?.[1],
    );
    const insulinY = Number(
      insulinTransform.match(/translate\([^ ]+ ([^)]+)\)/)?.[1],
    );
    expect(insulinY).toBeLessThan(anchorY);
    expect(foodY).toBeGreaterThan(anchorY);
    expect(
      Number(foodMarker?.querySelector("circle")?.getAttribute("r")),
    ).toBeGreaterThanOrEqual(12);
    expect(
      Number(insulinMarker?.querySelector("circle")?.getAttribute("r")),
    ).toBeGreaterThanOrEqual(12);
    expect(
      foodMarker?.querySelector(".ns-treatment-value")?.getAttribute("y"),
    ).toMatch(/^\d/);
    expect(
      insulinMarker?.querySelector(".ns-treatment-value")?.getAttribute("y"),
    ).toMatch(/^-/);
    expect(foodMarker?.querySelector(".ns-treatment-link")).toBeInTheDocument();
    expect(
      insulinMarker?.querySelector(".ns-treatment-link"),
    ).toBeInTheDocument();
  });

  test("dedupes near-identical insulin markers from re-import", () => {
    mockedUseDashboard.mockImplementation(
      (_from, _to, mode) =>
        ({
          data: {
            ...dashboard(mode),
            insulin_events: [
              {
                event_type: "Insulin",
                insulin_units: 1.5,
                notes: null,
                timestamp: "2026-07-12T07:00:00.000Z",
              },
              {
                event_type: "Insulin",
                insulin_units: 1.5,
                notes: null,
                timestamp: "2026-07-12T07:00:00.774Z",
              },
            ],
          },
          error: null,
          isLoading: false,
        }) as ReturnType<typeof useGlucoseDashboard>,
    );

    const { container } = render(
      <MemoryRouter>
        <NightscoutPage />
      </MemoryRouter>,
    );

    expect(container.querySelectorAll(".ns-treatment--insulin")).toHaveLength(
      1,
    );
  });

  test("renders the 90-minute personal forecast as colored points", () => {
    const { container } = render(
      <MemoryRouter>
        <NightscoutPage />
      </MemoryRouter>,
    );

    expect(container.querySelectorAll(".ns-forecast-point")).toHaveLength(18);
    expect(
      container.querySelectorAll(".ns-forecast-point--in_range"),
    ).toHaveLength(17);
    expect(container.querySelectorAll(".ns-forecast-point--high")).toHaveLength(
      1,
    );
    expect(screen.getByText(/\+90 мин/)).toBeInTheDocument();
    expect(screen.getByText(/MAE 1\.45/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Нормализованный" }));
    expect(mockedUsePrediction).toHaveBeenCalledWith("normalized");
  });

  test("opens one grouped calculation from either carbohydrate marker", () => {
    mockedUseDashboard.mockImplementation((_from, _to, mode) => {
      const data = dashboard(mode);
      return {
        data: {
          ...data,
          food_events: [
            {
              carbs_g: 55,
              kcal: 420,
              timestamp: "2026-07-12T06:55:00Z",
              title: "Основное",
            },
            {
              carbs_g: 28,
              kcal: 180,
              timestamp: "2026-07-12T06:58:00Z",
              title: "Дополнение",
            },
          ],
        },
        error: null,
        isLoading: false,
      } as unknown as ReturnType<typeof useGlucoseDashboard>;
    });
    mockedUseEpisodes.mockReturnValue({
      data: {
        from_datetime: "2026-07-12T04:00:00Z",
        to_datetime: "2026-07-12T07:00:00Z",
        episodes: [
          {
            end_at: "2026-07-12T07:00:00Z",
            insulin: [],
            key: "grouped-meal",
            kind: "food",
            meal_ids: [
              "11111111-1111-1111-1111-111111111111",
              "22222222-2222-2222-2222-222222222222",
            ],
            start_at: "2026-07-12T06:55:00Z",
            total_carbs_g: 83,
            total_insulin_units: 8.5,
            total_kcal: 600,
          },
        ],
      },
      error: null,
      isLoading: false,
    } as unknown as ReturnType<typeof useGlucoseEpisodes>);

    render(
      <MemoryRouter>
        <NightscoutPage />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Основное: 55.0 г углеводов",
      }),
    );
    expect(
      screen.getByRole("dialog", { name: "Инсулин для приёма" }),
    ).toBeInTheDocument();
    expect(screen.getByText("55 г + 28 г")).toBeInTheDocument();
    expect(screen.getByText("4.1 Ед")).toBeInTheDocument();
    expect(screen.getByText("8.5 Ед")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Дополнение: 28.0 г углеводов",
      }),
    );
    expect(screen.getByText("55 г + 28 г")).toBeInTheDocument();
    expect(screen.getByText("8.5 Ед")).toBeInTheDocument();
  });

  test("records an actual dose when the grouped meal has none", async () => {
    createInsulin.mockResolvedValue({
      editable: true,
      enteredBy: "glucotracker",
      eventType: "Meal Bolus",
      id: "33333333-3333-3333-3333-333333333333",
      insulin_type: null,
      insulin_units: 4.2,
      nightscout_id: "nightscout-actual",
      notes: null,
      timestamp: "2026-07-12T06:55:00Z",
    });

    render(
      <MemoryRouter>
        <NightscoutPage />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Завтрак: 42.0 г углеводов",
      }),
    );
    fireEvent.change(screen.getByLabelText("Введено инсулина"), {
      target: { value: "4,2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Записать" }));

    await waitFor(() =>
      expect(createInsulin).toHaveBeenCalledWith(
        expect.objectContaining({
          insulin_units: 4.2,
          recorded_at: "2026-07-12T06:55:00Z",
        }),
      ),
    );
    expect(await screen.findByText("4.2 Ед")).toBeInTheDocument();
  });

  test("shows meal plus correction and the calculated total", async () => {
    mockedUseRecommendation.mockImplementation((_mealIds, target) => {
      const ready = target === 6;
      return {
        data: {
          confidence: "medium",
          correction_glucose_mmol_l: ready ? 8.2 : null,
          correction_iob_units: ready ? 0.4 : null,
          correction_isf_mmol_l_per_unit: ready ? 1.5 : null,
          correction_projected_glucose_mmol_l: ready ? 8.4 : null,
          correction_status: ready ? "ready" : "target_required",
          correction_target_mmol_l: ready ? 6 : null,
          correction_trend_mmol_l_per_min: ready ? 0.02 : null,
          correction_units: ready ? 1.2 : null,
          matched_episode_count: 5,
          matches: [],
          meal_ids: ["11111111-1111-1111-1111-111111111111"],
          method_version: "historical-episode-median-v1",
          range_high_units: 4.3,
          range_low_units: 3.8,
          recommended_units: 4.1,
          status: "ready",
          target_carbs_g: 42,
          target_kcal: 510,
          total_range_high_units: ready ? 5.5 : null,
          total_range_low_units: ready ? 5.0 : null,
          total_recommended_units: ready ? 5.3 : null,
        },
        error: null,
        isError: false,
        isLoading: false,
      } as unknown as ReturnType<typeof useInsulinRecommendation>;
    });

    render(
      <MemoryRouter>
        <NightscoutPage />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Завтрак: 42.0 г углеводов",
      }),
    );
    fireEvent.change(screen.getByLabelText("Личная цель глюкозы"), {
      target: { value: "6,0" },
    });

    await waitFor(() =>
      expect(mockedUseRecommendation).toHaveBeenLastCalledWith(
        ["11111111-1111-1111-1111-111111111111"],
        6,
      ),
    );
    expect(screen.getByText("1.2 Ед")).toBeInTheDocument();
    expect(screen.getByText("5.3 Ед")).toBeInTheDocument();
    expect(screen.getByText(/Глюкоза 8.2 → 8.4 ммоль\/л/)).toBeInTheDocument();
  });
});
