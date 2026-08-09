import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { TherapyAnalysisResponse } from "../../api/client";
import {
  useGlucoseTherapyAnalysis,
  useTopUpDose,
} from "../glucose/useGlucoseDashboard";
import { TherapyAnalysisPage } from "./TherapyAnalysisPage";

vi.mock("../glucose/useGlucoseDashboard", () => ({
  useGlucoseTherapyAnalysis: vi.fn(),
  useTopUpDose: vi.fn(),
}));

const mockedUseAnalysis = vi.mocked(useGlucoseTherapyAnalysis);
const mockedUseTopUp = vi.mocked(useTopUpDose);

const emptyMetric = {
  confidence: "none" as const,
  q1: null,
  q3: null,
  sample_count: 0,
  value: null,
};

const analysis: TherapyAnalysisResponse = {
  basal_profile: {
    autotune_isf_mmol_l_per_unit: 3.6,
    autotuned_hour_count: 1,
    configured_daily_basal_units: 19.9,
    compressions: [
      {
        projected_daily_basal_units: 19.93,
        slots: Array.from({ length: 24 }, (_, hour) => {
          const configured =
            hour < 3 ? 0.8 : hour < 12 ? 0.7 : hour < 16 ? 0.8 : 1;
          return {
            autotuned_basal_u_per_hour: hour === 2 ? 0.83 : configured,
            autotuned_hour_count: hour === 2 ? 1 : 0,
            basal_adjustment_u_per_hour: hour === 2 ? 0.03 : 0,
            configured_basal_u_per_hour: configured,
            end_hour: hour + 1,
            equivalent_drift_mmol_l_per_hour: hour === 2 ? 0.1 : 0,
            evidence_window_count: hour === 2 ? 5 : 0,
            label: `${hour.toString().padStart(2, "0")}:00–${(hour + 1).toString().padStart(2, "0")}:00`,
            start_hour: hour,
          };
        }),
        window_count: 24,
      },
      {
        projected_daily_basal_units: 19.93,
        slots: [
          [0, 6, 0.75, 0.755, 0.005, 0.02, 5, 1],
          [6, 12, 0.7, 0.7, 0, 0, 0, 0],
          [12, 18, 0.867, 0.867, 0, 0, 0, 0],
          [18, 24, 1, 1, 0, 0, 0, 0],
        ].map(
          ([start, end, configured, autotuned, adjustment, drift, evidence, tuned]) => ({
            autotuned_basal_u_per_hour: autotuned,
            autotuned_hour_count: tuned,
            basal_adjustment_u_per_hour: adjustment,
            configured_basal_u_per_hour: configured,
            end_hour: end,
            equivalent_drift_mmol_l_per_hour: drift,
            evidence_window_count: evidence,
            label: `${start.toString().padStart(2, "0")}:00–${end.toString().padStart(2, "0")}:00`,
            start_hour: start,
          }),
        ),
        window_count: 4,
      },
    ],
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
      configured_basal_u_per_hour:
        hour < 3 ? 0.8 : hour < 12 ? 0.7 : hour < 16 ? 0.8 : 1,
      basal_adjustment_u_per_hour: hour === 2 ? 0.03 : null,
      autotuned_basal_u_per_hour: hour === 2 ? 0.83 : null,
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
      quiet_day_count: hour === 2 ? 4 : 0,
      // The middle half straddles zero here, so this hour is a median of noise
      // rather than a finding, and no test is suggested from it.
      discrepancy_confident: false,
      signal: hour === 2 ? ("stable" as const) : ("insufficient" as const),
      unknown_hr_drift_mmol_l_per_hour: emptyMetric,
    })),
    unknown_hr_window_count: 7,
    test_suggestion: null,
    projected_daily_basal_units: 19.93,
    washout_minutes: 240,
    window_minutes: 60,
  },
  bin_hours: 4,
  computed_at: "2026-07-31T12:00:00Z",
  from_date: "2026-05-03",
  icr_horizon_minutes: 120,
  isf_horizon_minutes: 240,
  isf_source: "correction_episodes",
  // Three isolated corrections against 41 boluses: an estimate, not a
  // measurement, and it must not be shown as ICR's equal.
  isf_identifiability: "thin",
  isf_note: "Изолированных коррекций: 3 из 41. Надёжно определяется только ICR.",
  isf_correction_count: 41,
  isf_cases: [
    {
      // The reported case: 1 U took 11.0 to 7.0, drifting back to 8.6 by the
      // horizon. Measured to the endpoint this reads 2.4 instead of 4.0.
      glucose_at_horizon: 8.6,
      glucose_nadir: 7,
      glucose_start: 11,
      insulin_units: 1,
      isf_mmol_l_per_unit: 4,
      minutes_to_nadir: 150,
      occurred_at: "2026-07-28T14:00:00",
    },
  ],
  isf_rejections: { not_isolated: 31, not_elevated: 6 },
  icr_excluded_for_activity: 2,
  icr_proposals: [
    {
      capped: false,
      confidence: "none",
      configured_icr_g_per_unit: 8,
      daypart: "morning",
      end_hour: 11,
      episode_count: 2,
      label: "Утро",
      measured_icr_g_per_unit: null,
      note: "нужно минимум 6 приёмов, есть 2",
      proposed_icr_g_per_unit: null,
      start_hour: 6,
    },
    {
      capped: false,
      confidence: "medium",
      configured_icr_g_per_unit: 9.3,
      daypart: "day",
      end_hour: 18,
      episode_count: 11,
      label: "День",
      measured_icr_g_per_unit: 10.4,
      note: null,
      proposed_icr_g_per_unit: 9.9,
      start_hour: 11,
    },
    {
      capped: false,
      confidence: "medium",
      configured_icr_g_per_unit: 10,
      daypart: "evening",
      end_hour: 6,
      episode_count: 9,
      label: "Вечер",
      measured_icr_g_per_unit: 10.1,
      note: null,
      proposed_icr_g_per_unit: 10.05,
      start_hour: 18,
    },
  ],
  model_version: "retrospective-therapy-analysis-v7",
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
    expect(
      screen.getByText("Basal autotune для плоского фона"),
    ).toBeInTheDocument();
    expect(screen.getByText("19.90 Ед/сут")).toBeInTheDocument();
    expect(screen.getByText("0.83 Ед/ч")).toBeInTheDocument();
    expect(screen.getByText(/Quiet-drift normalized/i)).toBeInTheDocument();
  });

  test("puts the configured ratio next to what the data implies", () => {
    render(
      <MemoryRouter>
        <TherapyAnalysisPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("Настройки против данных")).toBeInTheDocument();
    // Configured 9.3 against a measured 10.4, proposed 9.9 — a real move.
    expect(screen.getByText("9.3")).toBeInTheDocument();
    expect(screen.getByText("10.4")).toBeInTheDocument();
    expect(screen.getByText("9.9")).toBeInTheDocument();
    // Evening lands within a tenth of what is configured: nothing to do.
    expect(screen.getByText("без изменений")).toBeInTheDocument();
    // A slot with two episodes proposes nothing and says why.
    expect(
      screen.getByText("нужно минимум 6 приёмов, есть 2"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Рядом с нагрузкой исключено приёмов: 2/),
    ).toBeInTheDocument();
  });

  test("compresses the hourly basal profile to four evidence-aware windows", () => {
    render(
      <MemoryRouter>
        <TherapyAnalysisPage />
      </MemoryRouter>,
    );

    const heading = screen.getByText("Basal autotune для плоского фона");
    const section = heading.closest("section");
    expect(section).not.toBeNull();
    expect(section?.querySelectorAll("tbody tr")).toHaveLength(24);

    const slider = screen.getByRole("slider", {
      name: "Количество временных окон",
    });
    fireEvent.change(slider, { target: { value: "4" } });

    expect(slider).toHaveValue("4");
    expect(section?.querySelectorAll("tbody tr")).toHaveLength(4);
    expect(screen.getByText("00:00–06:00")).toBeInTheDocument();
    expect(screen.getByText("18:00–24:00")).toBeInTheDocument();
    expect(screen.getByText(/Суточная доза сохраняется/)).toBeInTheDocument();
  });

  test("says out loud that the ISF number rests on thin evidence", () => {
    render(
      <MemoryRouter>
        <TherapyAnalysisPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByText(/Изолированных коррекций: 3 из 41/),
    ).toBeInTheDocument();
  });

  test("shows the corrections the ISF median was built from", () => {
    render(
      <MemoryRouter>
        <TherapyAnalysisPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("Из чего сложился ISF")).toBeInTheDocument();
    expect(screen.getByText("1 из 41 коррекций за период")).toBeInTheDocument();
    // The fall it was measured from, and the endpoint the old method used.
    expect(screen.getByText("11.0")).toBeInTheDocument();
    expect(screen.getByText("7.0")).toBeInTheDocument();
    expect(screen.getByText("8.6")).toBeInTheDocument();
    expect(screen.getByText("4.00")).toBeInTheDocument();
    expect(
      screen.getByText(/рядом была еда или другой болюс — 31/),
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

describe("предложение базального теста", () => {
  const suggestion = {
    conservative_drift_mmol_l_per_hour: -1.02,
    day_count: 6,
    direction: "high" as const,
    drift_mmol_l_per_hour: -1.1,
    end_hour: 22,
    expected_change_u_per_hour: -0.31,
    fasting_hours: 4,
    label: "20:00—22:00",
    start_hour: 20,
    window_count: 12,
  };

  const renderWithIob = (iobUnits: number | null) => {
    mockedUseAnalysis.mockReturnValue({
      data: {
        ...analysis,
        basal_profile: {
          ...analysis.basal_profile,
          test_suggestion: suggestion,
        },
      },
      isError: false,
      isLoading: false,
    } as ReturnType<typeof useGlucoseTherapyAnalysis>);
    mockedUseTopUp.mockReturnValue({
      data: iobUnits == null ? undefined : { iob_units: iobUnits },
      isSuccess: iobUnits != null,
    } as ReturnType<typeof useTopUpDose>);
    render(
      <MemoryRouter>
        <TherapyAnalysisPage />
      </MemoryRouter>,
    );
  };

  test("называет отрезок и на чём он стоит", () => {
    renderWithIob(0);

    expect(screen.getByText("Базальный тест голодом")).toBeVisible();
    expect(screen.getByText(/20:00—22:00/)).toBeVisible();
    expect(screen.getByText("6 дн · 12 окон")).toBeVisible();
    expect(screen.getByText("-0.31 Ед/ч")).toBeVisible();
  });

  test("активный инсулин закрывает кнопку", () => {
    // The segment measures background drift, and a working bolus is exactly
    // the thing that would drown it. Readiness is the live number, not a note
    // in the protocol asking the reader to check.
    renderWithIob(2.4);

    expect(screen.getByText(/Активный инсулин 2\.40 Ед/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Начать тест" })).toBeDisabled();
  });

  test("без активного инсулина отрезок можно начать", () => {
    renderWithIob(0);

    expect(screen.getByText(/Активного инсулина нет/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Начать тест" })).toBeEnabled();
  });
});
