import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { GlucoseDashboardResponse, GlucoseMode } from "../../api/client";
import { useGlucoseDashboard } from "../glucose/useGlucoseDashboard";
import { NightscoutPage } from "./NightscoutPage";

vi.mock("../glucose/useGlucoseDashboard", () => ({
  useGlucoseDashboard: vi.fn(),
}));

const mockedUseDashboard = vi.mocked(useGlucoseDashboard);

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
});
