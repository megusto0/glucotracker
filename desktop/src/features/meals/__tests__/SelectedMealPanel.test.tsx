import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { MealResponse } from "../../../api/client";
import { SelectedMealPanel } from "../MealLedger";
import { useSettingsStore } from "../../settings/settingsStore";

function buildMeal(): MealResponse {
  return {
    id: "meal-1",
    eaten_at: "2026-05-05T12:13:00.000Z",
    title: "Паста с курицей",
    note: null,
    status: "accepted",
    source: "manual",
    total_carbs_g: 34,
    total_protein_g: 21,
    total_fat_g: 15,
    total_fiber_g: 6,
    total_kcal: 540,
    confidence: 0.82,
    nightscout_synced_at: null,
    nightscout_id: null,
    nightscout_sync_status: "not_synced",
    created_at: "2026-05-05T12:13:00.000Z",
    updated_at: "2026-05-05T12:13:00.000Z",
    thumbnail_url: null,
    items: [
      {
        id: "item-1",
        meal_id: "meal-1",
        name: "Паста",
        brand: null,
        grams: 150,
        serving_text: "150 г",
        carbs_g: 34,
        protein_g: 21,
        fat_g: 15,
        fiber_g: 6,
        kcal: 540,
        confidence: 0.82,
        confidence_reason: null,
        source_kind: "manual",
        calculation_method: "manual",
        assumptions: [],
        evidence: {},
        warnings: [],
        pattern_id: null,
        product_id: null,
        photo_id: null,
        image_url: null,
        image_cache_path: null,
        source_image_url: null,
        position: 0,
        created_at: "2026-05-05T12:13:00.000Z",
        updated_at: "2026-05-05T12:13:00.000Z",
      },
    ],
    photos: [],
  };
}

function renderPanel(width = 1024, meal = buildMeal()) {
  useSettingsStore.setState({ baseUrl: "http://api.test", token: "" });
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: width,
    writable: true,
  });
  window.dispatchEvent(new Event("resize"));

  return render(
    <QueryClientProvider client={queryClient}>
      <div style={{ width }}>
        <SelectedMealPanel
          meal={meal}
          onCreateFromWeight={() => undefined}
          onDelete={() => undefined}
          onUpdateItemWeight={() => undefined}
          onUpdateName={() => undefined}
          onUpdateTime={() => undefined}
        />
      </div>
    </QueryClientProvider>,
  );
}

function appearsBefore(left: Element, right: Element) {
  return (
    left.compareDocumentPosition(right) & Node.DOCUMENT_POSITION_FOLLOWING
  );
}

test("renders panel sections in strict task order", () => {
  const { container } = renderPanel();
  const scroll = container.querySelector(".selected-panel-scroll");
  expect(scroll?.firstElementChild).toHaveAttribute("data-testid", "panel-headline");

  const summary = screen.getByTestId("panel-summary");
  const quickEdit = screen.getByTestId("panel-quick-edit");
  const repeat = screen.getByTestId("panel-repeat-create");
  const sourceConfidence = screen.getByTestId("panel-source-confidence");

  expect(appearsBefore(summary, quickEdit)).toBeTruthy();
  expect(appearsBefore(quickEdit, repeat)).toBeTruthy();
  expect(appearsBefore(repeat, sourceConfidence)).toBeTruthy();

  const model = screen.getByRole("button", { name: "Оценка модели" });
  const components = screen.getByRole("button", { name: "Компоненты" });
  const assumptions = screen.getByRole("button", { name: "Допущения" });
  const raw = screen.getByRole("button", { name: "Исходные данные" });
  const nightscout = screen.getByRole("button", {
    name: "Синхронизация Nightscout",
  });

  expect(appearsBefore(model, components)).toBeTruthy();
  expect(appearsBefore(components, assumptions)).toBeTruthy();
  expect(appearsBefore(assumptions, raw)).toBeTruthy();
  expect(appearsBefore(raw, nightscout)).toBeTruthy();
  expect(appearsBefore(sourceConfidence, model)).toBeTruthy();
});

test("shows macro values once in one clean summary row", () => {
  renderPanel();
  const summary = screen.getByTestId("panel-summary");
  expect(within(summary).getByText("У 34 г / Б 21 г / Ж 15 г / К 540 ккал")).toBeInTheDocument();
  expect(within(summary).queryByText(/% ОСВ/)).not.toBeInTheDocument();
  expect(screen.queryByText(/% ОСВ/)).not.toBeInTheDocument();
  expect(summary.querySelectorAll(".panel-summary-one-line")).toHaveLength(1);
});

test("source and confidence stay below edit sections and above diagnostic accordions", () => {
  renderPanel();
  const headline = screen.getByTestId("panel-headline");
  const repeat = screen.getByTestId("panel-repeat-create");
  const sourceConfidence = screen.getByTestId("panel-source-confidence");
  const model = screen.getByRole("button", { name: "Оценка модели" });

  expect(appearsBefore(headline, sourceConfidence)).toBeTruthy();
  expect(appearsBefore(repeat, sourceConfidence)).toBeTruthy();
  expect(appearsBefore(sourceConfidence, model)).toBeTruthy();
  expect(within(sourceConfidence).getByText("Источник / достоверность")).toBeInTheDocument();
});

test("quick-edit fields are labeled and actions use exact button titles", () => {
  renderPanel();
  const quickEdit = screen.getByTestId("panel-quick-edit");
  expect(screen.getByLabelText("Название")).toBeInTheDocument();
  expect(screen.getByLabelText("Время")).toBeInTheDocument();
  expect(screen.getByLabelText("Вес записи")).toBeInTheDocument();
  expect(within(quickEdit).getAllByRole("button", { name: "Сохранить" })).toHaveLength(3);
});

test("quick-edit focus order is keyboard accessible", async () => {
  const user = userEvent.setup();
  renderPanel();
  const nameInput = screen.getByLabelText("Название");
  const timeInput = screen.getByLabelText("Время");
  const weightInput = screen.getByLabelText("Вес записи");
  const weightSave = within(screen.getByTestId("panel-quick-edit")).getAllByRole("button", {
    name: "Сохранить",
  })[2];

  await user.tab();
  expect(nameInput).toHaveFocus();
  await user.tab();
  expect(timeInput).toHaveFocus();
  await user.tab();
  expect(weightInput).toHaveFocus();
  await user.tab();
  expect(weightSave).toHaveFocus();
});

test("create another portion section is fully present with helper text, chips and prefills", () => {
  renderPanel(320);
  expect(screen.getByText("Создать ещё порцию")).toBeInTheDocument();
  expect(
    screen.getByText("Создаст новую запись. Текущая не изменится."),
  ).toBeInTheDocument();
  const gramsInput = screen.getByLabelText("Граммы") as HTMLInputElement;
  fireEvent.click(screen.getByRole("button", { name: "127 г" }));
  expect(gramsInput.value).toBe("127");
  fireEvent.click(screen.getByRole("button", { name: "текущий вес" }));
  expect(gramsInput.value).toBe("150");
});

test("required top controls remain visible for entries with missing item data", () => {
  renderPanel(320, {
    ...buildMeal(),
    confidence: null,
    items: [],
    title: "Запись без компонентов",
    total_carbs_g: 0,
    total_fat_g: 0,
    total_fiber_g: 0,
    total_kcal: 0,
    total_protein_g: 0,
  });

  expect(screen.getByTestId("panel-headline")).toHaveTextContent("Запись без компонентов");
  expect(screen.getByText("У 0 г / Б 0 г / Ж 0 г / К 0 ккал")).toBeInTheDocument();
  expect(screen.getByLabelText("Название")).toBeInTheDocument();
  expect(screen.getByLabelText("Время")).toBeInTheDocument();
  expect(screen.getByLabelText("Вес записи")).toBeDisabled();
  expect(screen.getByText("Создать ещё порцию")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "100 г" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "127 г" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "текущий вес" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Создать" })).toBeDisabled();
  expect(screen.getByTestId("panel-source-confidence")).toHaveTextContent("нет данных");
});

test("visual regression snapshot at 320px", () => {
  const { container } = renderPanel(320);
  expect(container.firstChild).toMatchSnapshot();
});

test("visual regression snapshot at 768px", () => {
  const { container } = renderPanel(768);
  expect(container.firstChild).toMatchSnapshot();
});

test("visual regression snapshot at 1920px", () => {
  const { container } = renderPanel(1920);
  expect(container.firstChild).toMatchSnapshot();
});
