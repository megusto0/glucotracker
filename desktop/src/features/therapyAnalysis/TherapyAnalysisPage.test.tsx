import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { TherapyAnalysisResponse } from "../../api/client";
import { useGlucoseTherapyAnalysis } from "../glucose/useGlucoseDashboard";
import { TherapyAnalysisPage } from "./TherapyAnalysisPage";

vi.mock("../glucose/useGlucoseDashboard", () => ({
  useGlucoseTherapyAnalysis: vi.fn(),
}));

const mockedUseAnalysis = vi.mocked(useGlucoseTherapyAnalysis);

const emptyMetric = {
  confidence: "none" as const,
  q1: null,
  q3: null,
  sample_count: 0,
  value: null,
};

const analysis: TherapyAnalysisResponse = {
  basal_profile: {
    elevated_hr_threshold_bpm: 82,
    elevated_hr_window_count: 4,
    quiet_window_count: 18,
    resting_reference_bpm: 59,
    slots: Array.from({ length: 24 }, (_, hour) => ({
      elevated_hr_drift_mmol_l_per_hour:
        hour === 18
          ? {
              confidence: "low" as const,
              q1: -0.9,
              q3: -0.5,
              sample_count: 2,
              value: -0.7,
            }
          : emptyMetric,
      hour,
      label: `${hour.toString().padStart(2, "0")}:00`,
      quiet_drift_mmol_l_per_hour:
        hour === 2
          ? {
              confidence: "medium" as const,
              q1: -0.1,
              q3: 0.2,
              sample_count: 5,
              value: 0.1,
            }
          : emptyMetric,
      signal: hour === 2 ? ("stable" as const) : ("insufficient" as const),
      unknown_hr_drift_mmol_l_per_hour: emptyMetric,
    })),
    unknown_hr_window_count: 7,
    washout_minutes: 240,
    window_minutes: 60,
  },
  bin_hours: 4,
  computed_at: "2026-07-31T12:00:00Z",
  from_date: "2026-05-03",
  icr_horizon_minutes: 120,
  isf_horizon_minutes: 240,
  isf_source: "correction_episodes",
  model_version: "retrospective-therapy-analysis-v2",
  notes: ["Использованы только чистые случаи."],
  overall_icr_g_per_unit: {
    confidence: "medium",
    q1: 8.8,
    q3: 10.7,
    sample_count: 6,
    value: 9.6,
  },
  overall_isf_mmol_l_per_unit: {
    confidence: "low",
    q1: 2.3,
    q3: 2.7,
    sample_count: 3,
    value: 2.5,
  },
  period_days: 90,
  slots: [
    {
      end_hour: 4,
      icr_g_per_unit: emptyMetric,
      isf_mmol_l_per_unit: emptyMetric,
      label: "00:00–04:00",
      start_hour: 0,
    },
    {
      end_hour: 12,
      icr_g_per_unit: {
        confidence: "medium",
        q1: 8.5,
        q3: 10.2,
        sample_count: 4,
        value: 9.2,
      },
      isf_mmol_l_per_unit: {
        confidence: "low",
        q1: 2.3,
        q3: 2.7,
        sample_count: 3,
        value: 2.5,
      },
      label: "08:00–12:00",
      start_hour: 8,
    },
  ],
  target_mmol_l: 6,
  to_date: "2026-07-31",
};

describe("TherapyAnalysisPage", () => {
  beforeEach(() => {
    mockedUseAnalysis.mockReturnValue({
      data: analysis,
      error: null,
      isError: false,
      isLoading: false,
    } as unknown as ReturnType<typeof useGlucoseTherapyAnalysis>);
  });

  test("shows robust overall and time-slot ICR/ISF evidence", () => {
    render(
      <MemoryRouter>
        <TherapyAnalysisPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("9.60 г/Ед")).toBeInTheDocument();
    expect(screen.getByText("08:00–12:00")).toBeInTheDocument();
    expect(screen.getAllByText("2.50 ммоль/л/Ед")).toHaveLength(2);
    expect(
      screen.getByText(/анализ прошлого, не рекомендация дозы/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Использованы только чистые случаи."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("24 часа: фоновая стабильность"),
    ).toBeInTheDocument();
    expect(screen.getByText(/высокий пульс от 82 уд\/мин/i)).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: "Фоновое изменение глюкозы по часам суток",
      }),
    ).toBeInTheDocument();
  });

  test("switches the long-term period", () => {
    render(
      <MemoryRouter>
        <TherapyAnalysisPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "180 дней" }));

    expect(mockedUseAnalysis).toHaveBeenLastCalledWith(180, 6);
    expect(
      screen.getByRole("button", { name: "180 дней" }),
    ).toHaveAttribute("aria-pressed", "true");
  });
});
