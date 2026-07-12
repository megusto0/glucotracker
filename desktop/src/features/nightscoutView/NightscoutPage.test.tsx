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
    food_events: [],
    from_datetime: "2026-07-12T04:00:00Z",
    insulin_events: [],
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
      current_glucose: normalized ? 6.2 : 5.5,
      current_glucose_at: "2026-07-12T07:00:00Z",
      drift_mmol_l_per_day: 0,
      sensor_age_days: 4,
      suspected_compression_count: 0,
    },
    to_datetime: "2026-07-12T07:00:00Z",
  };
}

describe("NightscoutPage", () => {
  beforeEach(() => {
    mockedUseDashboard.mockImplementation((_from, _to, mode) => ({
      data: dashboard(mode),
      error: null,
      isLoading: false,
    }) as ReturnType<typeof useGlucoseDashboard>);
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

    expect(screen.getByRole("button", { name: "Нормализованный" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText("6.2")).toBeInTheDocument();
    expect(container.querySelectorAll(".ns-point--normalized").length).toBeGreaterThan(0);
    expect(mockedUseDashboard).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      "normalized",
    );
  });
});
