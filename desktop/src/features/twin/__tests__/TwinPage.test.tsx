import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, test } from "vitest";
import { useSettingsStore } from "../../settings/settingsStore";
import { TwinPage } from "../TwinPage";
import { server } from "../../../tests/msw";

const params = {
  id: "twin-params-1",
  icr_morning: 11.8,
  icr_day: 12.4,
  icr_evening: 13.1,
  morning_start_minutes: 360,
  day_start_minutes: 660,
  evening_start_minutes: 1080,
  isf: 2.05,
  dia_minutes: 270,
  carb_duration_minutes: 180,
  baseline_drift_per_hour: 0.02,
  last_fit_at: "2026-04-27T08:00:00.000Z",
  last_fit_data_from: "2026-03-28T00:00:00.000Z",
  last_fit_data_to: "2026-04-27T00:00:00.000Z",
  last_fit_train_window_count: 96,
  last_fit_holdout_window_count: 24,
  last_fit_train_mae_mmol: 1.32,
  last_fit_holdout_mae_mmol: 1.68,
  last_fit_method: "least_squares",
  last_fit_converged: true,
  updated_at: "2026-04-27T08:00:00.000Z",
  is_fitted: true,
  hint: "ready",
};

function curve(overrides: Record<string, unknown> = {}) {
  return {
    from_datetime: "2026-04-28T08:00:00",
    to_datetime: "2026-04-28T10:00:00",
    points: [
      {
        timestamp: "2026-04-28T08:00:00",
        mmol: 6,
        ci_low: 6,
        ci_high: 6,
        confidence: 1,
        mode: "interpolation",
      },
      {
        timestamp: "2026-04-28T08:30:00",
        mmol: 7,
        ci_low: 6.5,
        ci_high: 7.5,
        confidence: 0.8,
        mode: "interpolation",
      },
      {
        timestamp: "2026-04-28T09:00:00",
        mmol: 8,
        ci_low: 8,
        ci_high: 8,
        confidence: 1,
        mode: "forecast",
      },
      {
        timestamp: "2026-04-28T09:30:00",
        mmol: 8.5,
        ci_low: 7.9,
        ci_high: 9.1,
        confidence: 0.75,
        mode: "forecast",
      },
    ],
    anchors: [
      { timestamp: "2026-04-28T08:00:00", mmol: 6, source: "fingerstick" },
      { timestamp: "2026-04-28T09:00:00", mmol: 8, source: "fingerstick" },
    ],
    food_events: [],
    insulin_events: [],
    params,
    notes: [],
    ...overrides,
  };
}

function renderTwin() {
  useSettingsStore.setState({
    baseUrl: "http://api.test",
    token: "dev-token",
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <TwinPage />
    </QueryClientProvider>,
  );
}

describe("TwinPage", () => {
  test("shows not fitted state with required disclaimer", async () => {
    const notFitted = {
      ...params,
      icr_morning: null,
      icr_day: null,
      icr_evening: null,
      isf: null,
      is_fitted: false,
      hint: "not_fitted",
    };
    server.use(
      http.get("http://api.test/twin/params", () => HttpResponse.json(notFitted)),
      http.get("http://api.test/twin/curve", () =>
        HttpResponse.json(curve({ points: [], anchors: [], params: notFitted })),
      ),
    );

    renderTwin();

    expect(await screen.findByText("Двойник ещё не подогнан.")).toBeInTheDocument();
    expect(screen.getByText(/не является медицинской рекомендацией/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Запустить подгонку" })).toBeDisabled();
  });

  test("renders ready chart with interpolation, forecast, CI band and anchors", async () => {
    renderTwin();

    expect(
      await screen.findByRole("img", { name: "График цифрового двойника" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("twin-interpolation-line")).toBeInTheDocument();
    expect(screen.getByTestId("twin-forecast-line")).toHaveAttribute(
      "stroke-dasharray",
      "7 6",
    );
    expect(screen.getByTestId("twin-ci-band")).toHaveAttribute("opacity", "0.15");
    expect(screen.getAllByTestId("twin-anchor")).toHaveLength(2);
  });

  test("shows stale warning", async () => {
    server.use(
      http.get("http://api.test/twin/params", () =>
        HttpResponse.json({ ...params, hint: "stale" }),
      ),
      http.get("http://api.test/twin/curve", () =>
        HttpResponse.json(curve({ params: { ...params, hint: "stale" } })),
      ),
    );

    renderTwin();

    expect(await screen.findByText(/Подгонка устарела/)).toBeInTheDocument();
  });

  test("does not crash when fitted response has no points", async () => {
    server.use(
      http.get("http://api.test/twin/curve", () =>
        HttpResponse.json(curve({ points: [], anchors: [] })),
      ),
    );

    renderTwin();

    expect(await screen.findByTestId("twin-chart-empty")).toBeInTheDocument();
  });
});
