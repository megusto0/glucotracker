export type ReportSlotKey = "breakfast" | "lunch" | "dinner" | "snack";

export type ReportKpi = {
  label: string;
  value: string;
  unit: string;
  caption: string;
};

export type ReportChip = {
  label: string;
};

export type MealProfileRow = {
  key: ReportSlotKey | "total";
  label: string;
  episodes: string;
  carbs: string;
  insulin: string;
  glucoseBefore: string;
  glucoseAfter: string;
  observedRatio: string;
};

export type DailySlotSummary = {
  carbs: number;
  insulin: number;
};

export type DailySummaryRow = {
  date: string;
  dateLabel: string;
  carbs: string;
  insulin: string;
  tir: string;
  hypo: string;
  breakfast: string;
  lunch: string;
  dinner: string;
  flagged: boolean;
};

export type ReportBottomMetric = {
  label: string;
  value: string;
  unit?: string;
};

export type EndocrinologistReportData = {
  appName: string;
  title: string;
  periodLabel: string;
  generatedLabel: string;
  chips: ReportChip[];
  warning: string | null;
  notes: string[];
  kpis: ReportKpi[];
  mealProfileRows: MealProfileRow[];
  dailyRows: DailySummaryRow[];
  shownDailyRows: DailySummaryRow[];
  dailyMedianRow: DailySummaryRow;
  dailyRowsNote: string | null;
  bottomMetrics: ReportBottomMetric[];
  footer: string;
};
