import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { apiClient, type AIModelsResponse } from "../../api/client";
import { AIModelsPage } from "./AIModelsPage";

vi.mock("../settings/settingsStore", () => ({
  useApiConfig: () => ({ baseUrl: "http://test", token: "test-token" }),
  useSettingsStore: (select: (s: unknown) => unknown) =>
    select({ currentUser: { id: "owner" } }),
}));
vi.mock("../../api/client", () => ({
  apiClient: { getAIModels: vi.fn(), updateAIModels: vi.fn() },
  apiErrorMessage: (e: Error) => e.message,
}));
const emptyStats = {
  attempts: 0,
  successes: 0,
  failures: 0,
  skipped: 0,
  timed_attempts: 0,
  timed_responses: 0,
  timed_requests: 0,
  confidence_samples: 0,
};
const snapshot: AIModelsResponse = {
  revision: 3,
  custom_routing: true,
  since: "2026-09-01T00:00:00Z",
  generated_at: "2026-09-22T12:00:00Z",
  history_truncated: false,
  history_total: 1,
  history_offset: 0,
  history: [
    {
      id: "00000000-0000-0000-0000-000000000001",
      created_at: "2026-09-22T10:00:00Z",
      request_type: "initial",
      status: "success",
      model_requested: "gemini-test",
      model_used: "gemini-test",
      provider: "gemini",
      fallback_used: false,
      latency_ms: 4000,
      attempts: [
        {
          provider: "gemini",
          model: "gemini-test",
          status: "error",
          latency_ms: 1000,
          response_latency_ms: 800,
          error_category: "timeout",
        },
      ],
    },
  ],
  models: [
    {
      ...emptyStats,
      provider: "gemini",
      model: "gemini-test",
      enabled: true,
      in_routing: true,
      available: true,
      attempts: 4,
      successes: 3,
      failures: 1,
      success_rate: 0.75,
      average_latency_ms: 2500,
      average_response_latency_ms: 2100,
      timed_responses: 4,
      average_request_latency_ms: 4000,
      timed_requests: 4,
      timed_attempts: 4,
      errors: [
        { category: "timeout", count: 1, last_at: "2026-09-22T10:00:00Z" },
      ],
    },
    {
      ...emptyStats,
      provider: "grok",
      model: "grok-test",
      enabled: true,
      in_routing: true,
      available: true,
      attempts: 0,
      errors: [],
    },
  ],
};
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AIModelsPage />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiClient.getAIModels).mockResolvedValue(structuredClone(snapshot));
  vi.mocked(apiClient.updateAIModels).mockImplementation(
    async (_config, payload) => ({
      ...snapshot,
      revision: 4,
      models: payload.models.map((m) => ({
        ...emptyStats,
        ...m,
        available: true,
        in_routing: true,
        errors: [],
      })),
    }),
  );
});
describe("model management", () => {
  test("shows request history and safe attempt details", async () => {
    setup();
    await screen.findByText("История запросов");
    expect(screen.getByText("1 за выбранный период")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Оценка еды"));
    expect(screen.getByText(/Запрошена: gemini-test/)).toBeInTheDocument();
    expect(screen.getByText("Ответ модели: 0,8 с")).toBeInTheDocument();
    expect(
      screen.getAllByText("Время ожидания истекло").length,
    ).toBeGreaterThan(0);
  });
  test("moves through request history pages", async () => {
    vi.mocked(apiClient.getAIModels).mockImplementation(
      async (_config, _days, offset) => ({
        ...snapshot,
        history_total: 31,
        history_offset: offset ?? 0,
        history: offset
          ? [
              {
                ...snapshot.history[0],
                id: "00000000-0000-0000-0000-000000000002",
              },
            ]
          : snapshot.history,
      }),
    );
    setup();
    await screen.findByText("31 за выбранный период");
    fireEvent.click(screen.getByRole("button", { name: "Далее" }));
    await waitFor(() =>
      expect(apiClient.getAIModels).toHaveBeenCalledWith(
        expect.anything(),
        30,
        30,
      ),
    );
    expect(await screen.findByText("31–31 из 31")).toBeInTheDocument();
  });
  test("shows real metrics and saves reordered, extended priority", async () => {
    setup();
    await screen.findByRole("article", { name: "Gemini gemini-test" });
    expect(screen.getAllByText("4 с").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Среднее время отдельного вызова: 2,5 с/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Среднее ожидание ответа модели: 2,1 с/),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Время ожидания истекло").length,
    ).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Поднять grok-test" }));
    fireEvent.change(screen.getByLabelText("Идентификатор модели"), {
      target: { value: "gemini-new" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Добавить модель" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить порядок" }));
    await waitFor(() => expect(apiClient.updateAIModels).toHaveBeenCalled());
    const payload = vi.mocked(apiClient.updateAIModels).mock.calls[0][1];
    expect(payload.revision).toBe(3);
    expect(payload.models.map((m) => m.model)).toEqual([
      "grok-test",
      "gemini-test",
      "gemini-new",
    ]);
  });
  test("drag and drop updates the priority sent to the server", async () => {
    setup();
    const source = await screen.findByRole("article", {
      name: "Grok grok-test",
    });
    const target = screen.getByRole("article", { name: "Gemini gemini-test" });
    fireEvent.dragStart(source.querySelector('[draggable="true"]')!, {
      dataTransfer: { setData: vi.fn(), effectAllowed: "" },
    });
    fireEvent.dragOver(target);
    fireEvent.drop(target);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить порядок" }));
    await waitFor(() => expect(apiClient.updateAIModels).toHaveBeenCalled());
    expect(
      vi.mocked(apiClient.updateAIModels).mock.calls[0][1].models[0].model,
    ).toBe("grok-test");
  });
  test("failed save keeps the draft and displays the failure", async () => {
    vi.mocked(apiClient.updateAIModels).mockRejectedValue(
      new Error("Порядок уже изменён"),
    );
    setup();
    await screen.findByRole("article", { name: "Gemini gemini-test" });
    fireEvent.click(screen.getByRole("button", { name: "Поднять grok-test" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить порядок" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Порядок уже изменён",
    );
    expect(
      screen.getByText("Есть несохранённые изменения"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Отменить изменения" }));
    expect(
      screen.getByRole("button", { name: "Сохранить порядок" }),
    ).toBeDisabled();
  });
});
