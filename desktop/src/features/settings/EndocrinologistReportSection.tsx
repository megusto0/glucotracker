import { FileText } from "lucide-react";
import { useMemo, useState } from "react";
import {
  apiClient,
  apiErrorMessage,
  type EndocrinologistReportResponse,
} from "../../api/client";
import { Button } from "../../design/primitives/Button";
import type {
  DailySummaryRow,
  EndocrinologistReportData,
  MealProfileRow,
  ReportBottomMetric,
} from "../reports/reportTypes";
import { savePdfFile } from "../../utils/savePdfFile";
import { useApiConfig } from "./settingsStore";

const pad = (value: number) => String(value).padStart(2, "0");

const localDateKey = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

const addDays = (date: Date, days: number) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);

const toLocalDateTimeString = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;

const initialRange = () => {
  const today = new Date();
  return {
    from: localDateKey(addDays(today, -13)),
    to: localDateKey(today),
  };
};

const rangeToDateTimes = (from: string, to: string) => ({
  fromDatetime: toLocalDateTimeString(new Date(`${from}T00:00:00`)),
  toDatetime: toLocalDateTimeString(new Date(`${to}T23:59:59`)),
});

type ApiDailyRow = EndocrinologistReportResponse["daily_rows"][number];
type ApiMealProfileRow =
  EndocrinologistReportResponse["meal_profile_rows"][number];

export function EndocrinologistReportSection() {
  const config = useApiConfig();
  const defaults = useMemo(initialRange, []);
  const [fromDate, setFromDate] = useState(defaults.from);
  const [toDate, setToDate] = useState(defaults.to);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  const canGenerate =
    Boolean(config.token.trim()) &&
    Boolean(fromDate) &&
    Boolean(toDate) &&
    fromDate <= toDate &&
    !isGenerating;

  const generate = async () => {
    setError(null);
    setStatus(null);
    setIsGenerating(true);
    try {
      const { fromDatetime, toDatetime } = rangeToDateTimes(fromDate, toDate);
      setStatus("Загружаю данные...");
      const settings = await apiClient.getNightscoutSettings(config);
      if (
        settings.configured &&
        (settings.sync_glucose || settings.import_insulin_events)
      ) {
        setStatus("Обновляю контекст Nightscout...");
        await apiClient.importNightscoutContext(config, {
          from_datetime: fromDatetime,
          to_datetime: toDatetime,
          sync_glucose: settings.sync_glucose,
          import_insulin_events: settings.import_insulin_events,
        });
      }

      setStatus("Собираю PDF...");
      const apiReport = await apiClient.getEndocrinologistReport(
        config,
        fromDate,
        toDate,
      );
      const reportData = mapReportData(apiReport);
      const [{ pdf }, { EndocrinologistReportPdf }] = await Promise.all([
        import("@react-pdf/renderer"),
        import("../reports/EndocrinologistReportPdf"),
      ]);
      const blob = await pdf(<EndocrinologistReportPdf data={reportData} />).toBlob();
      const bytes = new Uint8Array(await blob.arrayBuffer());

      setStatus("Выберите место сохранения...");
      const savedPath = await savePdfFile({
        bytes,
        defaultPath: `glucotracker-endocrinologist-${fromDate}_${toDate}.pdf`,
      });
      setStatus(savedPath ? "PDF сохранён." : "Сохранение отменено.");
    } catch (err) {
      setError(apiErrorMessage(err, "Не удалось сформировать PDF-отчёт."));
      setStatus(null);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <section className="grid gap-5 border-b border-[var(--hairline)] pb-8 last:border-b-0">
      <div className="grid gap-2">
        <h2 className="text-[24px] font-normal">Отчёт для врача</h2>
        <p className="max-w-[720px] text-[13px] leading-5 text-[var(--muted)]">
          PDF-отчёт на один лист A4: инсулин, глюкоза до/после еды,
          наблюдаемый УК и сводка по дням.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-[160px_160px_auto] sm:items-end">
        <label className="grid gap-2">
          <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
            От
          </span>
          <input
            className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent px-0 font-mono text-[14px] outline-none focus:border-[var(--fg)]"
            onChange={(event) => setFromDate(event.target.value)}
            type="date"
            value={fromDate}
          />
        </label>
        <label className="grid gap-2">
          <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
            До
          </span>
          <input
            className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent px-0 font-mono text-[14px] outline-none focus:border-[var(--fg)]"
            onChange={(event) => setToDate(event.target.value)}
            type="date"
            value={toDate}
          />
        </label>
        <Button
          disabled={!canGenerate}
          icon={<FileText size={18} />}
          onClick={() => void generate()}
          variant="primary"
        >
          {isGenerating ? "Генерирую..." : "Сгенерировать PDF"}
        </Button>
      </div>

      {fromDate > toDate ? (
        <p className="text-[13px] text-[var(--danger)]">
          Дата начала должна быть раньше даты конца.
        </p>
      ) : null}
      {!config.token.trim() ? (
        <p className="text-[13px] text-[var(--muted)]">
          Для отчёта нужен настроенный backend и bearer-токен.
        </p>
      ) : null}
      {status ? <p className="text-[13px] text-[var(--muted)]">{status}</p> : null}
      {error ? <p className="text-[13px] text-[var(--danger)]">{error}</p> : null}
      <p className="text-[11px] leading-5 text-[var(--muted)]">
        Отчёт информационный: он не предлагает дозы, коррекции, болюсы или
        медицинские решения.
      </p>
    </section>
  );
}

function mapReportData(
  data: EndocrinologistReportResponse,
): EndocrinologistReportData {
  return {
    appName: data.app_name,
    title: data.title,
    periodLabel: data.period_label,
    generatedLabel: data.generated_label,
    chips: data.chips,
    warning: data.warning ?? null,
    notes: data.notes ?? [],
    kpis: data.kpis,
    mealProfileRows: data.meal_profile_rows.map(mapMealProfileRow),
    dailyRows: data.daily_rows.map(mapDailyRow),
    shownDailyRows: data.shown_daily_rows.map(mapDailyRow),
    dailyMedianRow: mapDailyRow(data.daily_median_row),
    dailyRowsNote: data.daily_rows_note ?? null,
    bottomMetrics: data.bottom_metrics.map(mapBottomMetric),
    footer: data.footer,
  };
}

function mapMealProfileRow(row: ApiMealProfileRow): MealProfileRow {
  return {
    key: row.key as MealProfileRow["key"],
    label: row.label,
    episodes: row.episodes,
    carbs: row.carbs,
    insulin: row.insulin,
    glucoseBefore: row.glucose_before,
    glucoseAfter: row.glucose_after,
    observedRatio: row.observed_ratio,
  };
}

function mapDailyRow(row: ApiDailyRow): DailySummaryRow {
  return {
    date: row.date,
    dateLabel: row.date_label,
    carbs: row.carbs,
    insulin: row.insulin,
    tir: row.tir,
    hypo: row.hypo,
    breakfast: row.breakfast,
    lunch: row.lunch,
    dinner: row.dinner,
    flagged: row.flagged,
  };
}

function mapBottomMetric(
  row: EndocrinologistReportResponse["bottom_metrics"][number],
): ReportBottomMetric {
  return {
    label: row.label,
    value: row.value,
    unit: row.unit ?? undefined,
  };
}
