import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { TherapyReviewDayResponse } from "../../api/client";
import {
  useGlucoseTherapyReview,
  usePrefetchGlucoseTherapyReview,
  useRecalculateGlucoseTherapyReview,
} from "../glucose/useGlucoseDashboard";
import { TherapyReviewPage } from "./TherapyReviewPage";

vi.mock("../glucose/useGlucoseDashboard", () => ({
  useGlucoseTherapyReview: vi.fn(),
  usePrefetchGlucoseTherapyReview: vi.fn(),
  useRecalculateGlucoseTherapyReview: vi.fn(),
}));

const mockedUseReview = vi.mocked(useGlucoseTherapyReview);
const mockedUseRecalculation = vi.mocked(
  useRecalculateGlucoseTherapyReview,
);
const mockedUsePrefetch = vi.mocked(usePrefetchGlucoseTherapyReview);
const refetch = vi.fn();
const recalculate = vi.fn();
const prefetch = vi.fn();

const review: TherapyReviewDayResponse = {
  cached: true,
  computed_at: "2026-07-25T22:00:00Z",
  date: "2026-07-25",
  horizon_minutes: 120,
  model_version: "retrospective-therapy-review-v3",
  target_mmol_l: 6,
  body_states: [
    {
      confidence: "high",
      end_at: "2026-07-25T07:10:00",
      kind: "sleep",
      minutes: 430,
      source: "recorded",
      start_at: "2026-07-25T00:00:00",
      total_minutes: 430,
    },
    {
      confidence: "medium",
      end_at: "2026-07-25T18:35:00",
      kind: "activity",
      minutes: 35,
      peak_bpm: 148,
      source: "heart_rate",
      start_at: "2026-07-25T18:00:00",
      total_minutes: 35,
    },
  ],
  items: [
    {
      body_context: ["after_sleep"],
      // Ends on target after two hours above the high band: the case that used
      // to read as a clean episode.
      outcome_quality: "spike",
      peak_mmol_l: 13.1,
      peak_after_minutes: 40,
      nadir_mmol_l: 5.2,
      nadir_after_minutes: 120,
      minutes_above_high: 70,
      minutes_below_low: 0,
      trajectory: [6.2, 10.4, 13.1, 10.8, 7.1, 5.6, 5.2],
      trajectory_step_minutes: 20,
      actual_value: 8.5,
      adjusted_actual_value: 8.2,
      adjustment_status: "ready",
      calculated_value: 9.3,
      calculation_status: "ready",
      classification: "meal",
      confidence: "high",
      glucose_after_normalized: 5.2,
      glucose_after_raw: 3,
      glucose_start_normalized: 8.4,
      glucose_start_raw: 9.3,
      horizon_minutes: 120,
      isf_mmol_l_per_unit: 2.8,
      key: "lunch",
      notes: ["Еда 8.1 Ед + коррекция 1.2 Ед"],
      start_at: "2026-07-25T11:50:00+04:00",
      target_mmol_l: 6,
      title: "55 г + 28 г",
      total_carbs_g: 83,
      total_insulin_units: 8.5,
      value_unit: "U",
    },
    {
      outcome_quality: "in_range",
      peak_mmol_l: 6.7,
      peak_after_minutes: 0,
      nadir_mmol_l: 4.6,
      nadir_after_minutes: 60,
      minutes_above_high: 0,
      minutes_below_low: 0,
      trajectory: [6.7, 5.4, 4.6, 4.7, 4.9],
      trajectory_step_minutes: 30,
      actual_value: 7,
      adjusted_actual_value: 11.5,
      adjustment_status: "ready",
      calculated_value: 15,
      calculation_status: "ready",
      classification: "carb_correction",
      confidence: "high",
      glucose_after_normalized: 4.9,
      glucose_after_raw: 4.2,
      glucose_start_normalized: 6.7,
      glucose_start_raw: 5.1,
      horizon_minutes: 120,
      isf_mmol_l_per_unit: null,
      key: "rescue",
      notes: ["Без пищевого болюса"],
      start_at: "2026-07-25T12:30:00+04:00",
      target_mmol_l: 6,
      title: "7 г",
      total_carbs_g: 7,
      total_insulin_units: 0,
      value_unit: "g",
    },
  ],
};

describe("TherapyReviewPage", () => {
  beforeEach(() => {
    refetch.mockReset();
    recalculate.mockReset();
    prefetch.mockReset();
    mockedUsePrefetch.mockReturnValue(prefetch);
    mockedUseReview.mockReturnValue({
      data: review,
      error: null,
      isError: false,
      isFetching: false,
      isLoading: false,
      refetch,
    } as unknown as ReturnType<typeof useGlucoseTherapyReview>);
    mockedUseRecalculation.mockReturnValue({
      isPending: false,
      mutate: recalculate,
    } as unknown as ReturnType<typeof useRecalculateGlucoseTherapyReview>);
  });

  test("shows daily episodes with actual, calculated and hindsight-adjusted values", () => {
    render(
      <MemoryRouter>
        <TherapyReviewPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("55 г + 28 г")).toBeInTheDocument();
    expect(screen.getByText("Коррекция углеводами")).toBeInTheDocument();
    expect(screen.getByText("8.5 Ед")).toBeInTheDocument();
    expect(screen.getByText("9.3 Ед")).toBeInTheDocument();
    expect(screen.getByText("8.2 Ед")).toBeInTheDocument();
    expect(screen.getByText("7.0 g")).toBeInTheDocument();
    expect(screen.getByText("15.0 g")).toBeInTheDocument();
    expect(screen.getByText("11.5 g")).toBeInTheDocument();
    expect(screen.getAllByText("С поправкой по факту")).toHaveLength(2);
    expect(
      screen.getByText(/объяснение прошлого эпизода/i),
    ).toBeInTheDocument();
  });

  test("allows changing the outcome horizon and refreshing", () => {
    render(
      <MemoryRouter>
        <TherapyReviewPage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "180" },
    });
    expect(mockedUseReview).toHaveBeenLastCalledWith(
      expect.any(String),
      6,
      180,
    );

    fireEvent.click(screen.getByRole("button", { name: "Обновить разбор" }));
    expect(recalculate).toHaveBeenCalledWith({
      date: expect.any(String),
      targetMmolL: 6,
      horizonMinutes: 180,
    });
  });

  test("offers the adjacent long-term ICR and ISF analysis", () => {
    render(
      <MemoryRouter>
        <TherapyReviewPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("button", { name: "Анализ ICR и ISF" }),
    ).toBeInTheDocument();
  });

  test("an episode that spiked is not badged as clean just for landing on target", () => {
    render(
      <MemoryRouter>
        <TherapyReviewPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("был пик")).toBeInTheDocument();
    expect(screen.getByText(/пик 13\.1 · \+40 мин/)).toBeInTheDocument();
    expect(screen.getByText(/выше 10: 70 мин/)).toBeInTheDocument();
    // The carb rescue stayed in range throughout and keeps the clean badge.
    expect(screen.getByText("чисто")).toBeInTheDocument();
  });

  test("shows the day's sleep and effort, and marks the meal that followed sleep", () => {
    render(
      <MemoryRouter>
        <TherapyReviewPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("Контекст дня")).toBeInTheDocument();
    expect(screen.getByText(/сон 7 ч 10 мин/)).toBeInTheDocument();
    expect(screen.getByText(/нагрузок: 1/)).toBeInTheDocument();
    // The inferred workout has to say it came from heart rate, not the watch.
    expect(
      screen.getByText(/Нагрузка · 18:00–18:35 · 35 мин · по пульсу/),
    ).toBeInTheDocument();
    expect(screen.getByText("первый после сна")).toBeInTheDocument();
  });

  test("says so plainly when there is neither a session nor a pulse", () => {
    mockedUseReview.mockReturnValue({
      data: { ...review, body_states: [] },
      error: null,
      isError: false,
      isFetching: false,
      isLoading: false,
      refetch,
    } as unknown as ReturnType<typeof useGlucoseTherapyReview>);

    render(
      <MemoryRouter>
        <TherapyReviewPage />
      </MemoryRouter>,
    );

    expect(screen.getByText(/сон не найден/)).toBeInTheDocument();
    expect(screen.getByText(/восстановить/)).toBeInTheDocument();
  });

  test("does not report an empty day while a new date is still loading", () => {
    mockedUseReview.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isFetching: true,
      isLoading: false,
      refetch,
    } as unknown as ReturnType<typeof useGlucoseTherapyReview>);

    render(
      <MemoryRouter>
        <TherapyReviewPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByText("Собираю эпизоды, расчёты и исходы…"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("За этот день эпизодов не найдено."),
    ).not.toBeInTheDocument();
  });
});
