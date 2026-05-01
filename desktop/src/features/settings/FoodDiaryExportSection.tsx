import { useState } from "react";
import { apiClient, apiErrorMessage, type MealResponse } from "../../api/client";
import { Button } from "../../design/primitives/Button";
import { buildFoodDiaryTextReport } from "../../utils/mealTextReport";
import { saveTextFile } from "../../utils/saveTextFile";
import { useApiConfig } from "./settingsStore";

const PAGE_SIZE = 100;

async function fetchAllAcceptedMeals(
  config: ReturnType<typeof useApiConfig>,
): Promise<MealResponse[]> {
  const meals: MealResponse[] = [];
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;

  while (offset < total) {
    const page = await apiClient.listMeals(config, {
      limit: PAGE_SIZE,
      offset,
      status: "accepted",
    });
    meals.push(...page.items);
    total = page.total;
    if (!page.items.length) {
      break;
    }
    offset += page.items.length;
  }

  return meals;
}

const reportFileName = (meals: MealResponse[]) => {
  const sorted = [...meals].sort((left, right) =>
    left.eaten_at.localeCompare(right.eaten_at),
  );
  const first = sorted[0]?.eaten_at.slice(0, 10) ?? "empty";
  const last = sorted[sorted.length - 1]?.eaten_at.slice(0, 10) ?? "empty";
  return `glucotracker-food-diary-${first}_${last}.txt`;
};

export function FoodDiaryExportSection() {
  const config = useApiConfig();
  const [isExporting, setIsExporting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const exportDiary = async () => {
    setError(null);
    setStatus("Загружаю записи еды...");
    setIsExporting(true);
    try {
      const meals = await fetchAllAcceptedMeals(config);
      const text = buildFoodDiaryTextReport(meals);
      setStatus("Выберите место сохранения...");
      const savedPath = await saveTextFile({
        defaultPath: reportFileName(meals),
        text,
        title: "Сохранить дневник еды",
      });
      setStatus(
        savedPath
          ? `TXT сохранён. Записей: ${meals.length}.`
          : "Сохранение отменено.",
      );
    } catch (err) {
      setError(apiErrorMessage(err, "Не удалось сохранить дневник еды."));
      setStatus(null);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <section className="grid gap-5 border-b border-[var(--hairline)] pb-8 last:border-b-0">
      <div className="grid gap-2">
        <h2 className="text-[24px] font-normal">Экспорт еды</h2>
        <p className="max-w-[720px] text-[13px] leading-5 text-[var(--muted)]">
          TXT-файл по всем дням, где есть принятые записи: блюда, позиции,
          макросы и итоги по каждому дню.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          disabled={isExporting || !config.token.trim()}
          onClick={() => void exportDiary()}
          variant="primary"
        >
          {isExporting ? "Создаю TXT..." : "Создать TXT по всей еде"}
        </Button>
        {status ? <p className="text-[13px] text-[var(--muted)]">{status}</p> : null}
      </div>

      {!config.token.trim() ? (
        <p className="text-[13px] text-[var(--muted)]">
          Для экспорта нужен настроенный backend и bearer-токен.
        </p>
      ) : null}
      {error ? <p className="text-[13px] text-[var(--danger)]">{error}</p> : null}
    </section>
  );
}
