import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { TherapyReviewDayResponse } from "../../api/client";
import {
  useGlucoseTherapyReview,
  useRecalculateGlucoseTherapyReview,
} from "../glucose/useGlucoseDashboard";
import { TherapyReviewPage } from "./TherapyReviewPage";

vi.mock("../glucose/useGlucoseDashboard", () => ({
  useGlucoseTherapyReview: vi.fn(),
  useRecalculateGlucoseTherapyReview: vi.fn(),
}));

const mockedUseReview = vi.mocked(useGlucoseTherapyReview);
const mockedUseRecalculation = vi.mocked(
  useRecalculateGlucoseTherapyReview,
);
const refetch = vi.fn();
const recalculate = vi.fn();

const review: TherapyReviewDayResponse = {
  cached: true,
  computed_at: "2026-07-25T22:00:00Z",
  date: "2026-07-25",
  horizon_minutes: 120,
  model_version: "retrospective-therapy-review-v1",
  target_mmol_l: 6,
  items: [
    {
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
