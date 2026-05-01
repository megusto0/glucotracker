import type { MealResponse } from "../api/client";

const monthsRu: Record<string, string> = {
  "01": "января",
  "02": "февраля",
  "03": "марта",
  "04": "апреля",
  "05": "мая",
  "06": "июня",
  "07": "июля",
  "08": "августа",
  "09": "сентября",
  "10": "октября",
  "11": "ноября",
  "12": "декабря",
};

type Totals = {
  carbs: number;
  fat: number;
  fiber: number;
  kcal: number;
  protein: number;
};

type MealItem = NonNullable<MealResponse["items"]>[number];

const emptyTotals = (): Totals => ({
  carbs: 0,
  fat: 0,
  fiber: 0,
  kcal: 0,
  protein: 0,
});

const addMealTotals = (totals: Totals, meal: MealResponse) => {
  totals.carbs += meal.total_carbs_g ?? 0;
  totals.protein += meal.total_protein_g ?? 0;
  totals.fat += meal.total_fat_g ?? 0;
  totals.fiber += meal.total_fiber_g ?? 0;
  totals.kcal += meal.total_kcal ?? 0;
};

const formatNumber = (value?: number | null, digits = 1) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  const rounded = Number(value).toFixed(digits);
  return rounded.replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
};

const dayKey = (value: string) => value.slice(0, 10);

const timeLabel = (value: string) => value.slice(11, 16) || "—";

const dayLabel = (key: string) => {
  const [year, month, day] = key.split("-");
  return `${Number(day)} ${monthsRu[month] ?? month} ${year}`;
};

const macrosLine = (totals: Totals) =>
  `углеводы ${formatNumber(totals.carbs)} г; белки ${formatNumber(
    totals.protein,
  )} г; жиры ${formatNumber(totals.fat)} г; клетчатка ${formatNumber(
    totals.fiber,
  )} г; ккал ${formatNumber(totals.kcal, 0)}`;

const mealTotals = (meal: MealResponse): Totals => ({
  carbs: meal.total_carbs_g ?? 0,
  fat: meal.total_fat_g ?? 0,
  fiber: meal.total_fiber_g ?? 0,
  kcal: meal.total_kcal ?? 0,
  protein: meal.total_protein_g ?? 0,
});

const itemQuantity = (item: MealItem) => {
  const parts: string[] = [];
  if (item.grams !== null && item.grams !== undefined) {
    parts.push(`${formatNumber(item.grams)} г`);
  }
  if (item.serving_text && !parts.includes(item.serving_text)) {
    parts.push(item.serving_text);
  }
  return parts.length ? ` (${parts.join(", ")})` : "";
};

const itemTotals = (item: MealItem): Totals => ({
  carbs: item.carbs_g ?? 0,
  fat: item.fat_g ?? 0,
  fiber: item.fiber_g ?? 0,
  kcal: item.kcal ?? 0,
  protein: item.protein_g ?? 0,
});

export function buildFoodDiaryTextReport(meals: MealResponse[]) {
  const acceptedMeals = [...meals]
    .filter((meal) => meal.status === "accepted")
    .sort((left, right) => left.eaten_at.localeCompare(right.eaten_at));
  const days = new Map<string, MealResponse[]>();
  acceptedMeals.forEach((meal) => {
    const key = dayKey(meal.eaten_at);
    days.set(key, [...(days.get(key) ?? []), meal]);
  });

  const firstDay = acceptedMeals[0] ? dayLabel(dayKey(acceptedMeals[0].eaten_at)) : "—";
  const lastDay = acceptedMeals.length
    ? dayLabel(dayKey(acceptedMeals[acceptedMeals.length - 1].eaten_at))
    : "—";
  const lines = [
    "Glucotracker — еда за все дни с записями",
    `Период: ${firstDay} — ${lastDay}`,
    "Включены только записи со статусом accepted.",
    "",
  ];
  const periodTotals = emptyTotals();

  if (!acceptedMeals.length) {
    lines.push("Записей еды нет.");
    return `${lines.join("\n")}\n`;
  }

  [...days.entries()].forEach(([key, dayMeals]) => {
    const totals = emptyTotals();
    dayMeals.forEach((meal) => addMealTotals(totals, meal));
    Object.keys(periodTotals).forEach((key) => {
      const totalKey = key as keyof Totals;
      periodTotals[totalKey] += totals[totalKey];
    });

    lines.push(`## ${dayLabel(key)}`);
    lines.push(`Итого за день: ${macrosLine(totals)}`);
    lines.push("");

    dayMeals.forEach((meal) => {
      const items = meal.items ?? [];
      lines.push(`${timeLabel(meal.eaten_at)} — ${meal.title || "Приём пищи"}`);
      lines.push(`  Макросы: ${macrosLine(mealTotals(meal))}`);
      if (items.length) {
        lines.push("  Позиции:");
        items.forEach((item) => {
          const brand = item.brand ? ` — ${item.brand}` : "";
          lines.push(
            `    - ${item.name}${brand}${itemQuantity(item)}: ${macrosLine(
              itemTotals(item),
            )}`,
          );
        });
      }
      lines.push("");
    });
  });

  lines.push("## Итого за период");
  lines.push(`Углеводы: ${formatNumber(periodTotals.carbs)} г`);
  lines.push(`Белки: ${formatNumber(periodTotals.protein)} г`);
  lines.push(`Жиры: ${formatNumber(periodTotals.fat)} г`);
  lines.push(`Клетчатка: ${formatNumber(periodTotals.fiber)} г`);
  lines.push(`Ккал: ${formatNumber(periodTotals.kcal, 0)}`);

  return `${lines.join("\n")}\n`;
}
