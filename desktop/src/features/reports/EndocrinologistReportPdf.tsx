import {
  Document,
  Font,
  Page,
  StyleSheet,
  Text,
  View,
} from "@react-pdf/renderer";
import jetBrainsMono from "@fontsource/jetbrains-mono/files/jetbrains-mono-cyrillic-500-normal.woff?url";
import notoSansBold from "@fontsource/noto-sans/files/noto-sans-cyrillic-700-normal.woff?url";
import notoSansMedium from "@fontsource/noto-sans/files/noto-sans-cyrillic-500-normal.woff?url";
import notoSansRegular from "@fontsource/noto-sans/files/noto-sans-cyrillic-400-normal.woff?url";
import type {
  DailySummaryRow,
  EndocrinologistReportData,
  MealProfileRow,
  ReportBottomMetric,
  ReportKpi,
} from "./reportTypes";

Font.register({
  family: "NotoSans",
  fonts: [
    { src: notoSansRegular, fontWeight: 400 },
    { src: notoSansMedium, fontWeight: 500 },
    { src: notoSansBold, fontWeight: 700 },
  ],
});

Font.register({
  family: "JetBrainsMono",
  src: jetBrainsMono,
  fontWeight: 500,
});

Font.registerHyphenationCallback((word) => [word]);

const PAGE_WIDTH = 595.28;
const PAGE_HEIGHT = 841.89;
const MARGIN_X = 28;
const MARGIN_Y = 24;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN_X * 2;

const KPI_GAP = 6;
const KPI_CARD_WIDTH = (CONTENT_WIDTH - KPI_GAP * 3) / 4;
const KPI_CARD_HEIGHT = 54;

const TABLE_FONT = 7.5;
const ROW_H = 16;
const HEAD_H = 17;
const TOTAL_H = 17;

export function EndocrinologistReportPdf({
  data,
}: {
  data: EndocrinologistReportData;
}) {
  return (
    <Document
      author="glucotracker"
      subject="Informational T1D food diary report"
      title={data.title}
    >
      <Page size={{ width: PAGE_WIDTH, height: PAGE_HEIGHT }} style={styles.page}>
        <Header data={data} />
        <KpiBlock items={data.kpis} />
        <MealProfileSection rows={data.mealProfileRows} />
        <DailySection
          medianRow={data.dailyMedianRow}
          note={data.dailyRowsNote}
          rows={data.shownDailyRows}
        />
        <BottomStrip metrics={data.bottomMetrics} />
        <Text style={styles.footer}>{data.footer}</Text>
      </Page>
    </Document>
  );
}

function Header({ data }: { data: EndocrinologistReportData }) {
  return (
    <View style={styles.header} fixed>
      <View style={styles.headerRow}>
        <Text style={styles.appName}>{data.appName}</Text>
        <Text style={styles.subtitle}>
          {data.periodLabel} · {data.generatedLabel}
        </Text>
      </View>
      <Text style={styles.title}>Сводка за период</Text>
      <View style={styles.chipsRow}>
        {data.chips.map((chip) => (
          <View key={chip.label} style={styles.chip}>
            <Text style={styles.chipText}>{chip.label}</Text>
          </View>
        ))}
      </View>
      {data.warning ? (
        <View style={styles.warning}>
          <Text style={styles.warningIcon}>!</Text>
          <Text style={styles.warningText}>{data.warning}</Text>
        </View>
      ) : null}
      {data.notes.length ? (
        <Text style={styles.notes}>{data.notes.join(" · ")}</Text>
      ) : null}
    </View>
  );
}

function KpiBlock({ items }: { items: ReportKpi[] }) {
  const rows: ReportKpi[][] = [];
  for (let i = 0; i < items.length; i += 4) {
    rows.push(items.slice(i, i + 4));
  }

  return (
    <View style={styles.kpiBlock}>
      {rows.map((row, ri) => (
        <View key={ri} style={[styles.kpiRow, ri > 0 ? { marginTop: KPI_GAP } : {}]}>
          {row.map((item) => (
            <View key={item.label} style={styles.kpiCard}>
              <Text style={styles.kpiLabel}>{item.label}</Text>
              <View style={styles.kpiValueRow}>
                <Text style={styles.kpiValue}>{item.value}</Text>
                {item.unit ? <Text style={styles.kpiUnit}>{item.unit}</Text> : null}
              </View>
              <Text style={styles.kpiCaption}>{item.caption}</Text>
            </View>
          ))}
          {row.length < 4
            ? Array.from({ length: 4 - row.length }, (_, i) => (
                <View key={`empty-${i}`} style={styles.kpiCard} />
              ))
            : null}
        </View>
      ))}
    </View>
  );
}

const MEAL_COLS = [
  { key: "label", label: "Приём пищи", width: 100, align: "left" as const },
  { key: "episodes", label: "Эпиз.", width: 48, align: "center" as const },
  { key: "carbs", label: "Угл., г", width: 52, align: "center" as const },
  { key: "insulin", label: "Инс., ЕД", width: 56, align: "center" as const },
  { key: "glucoseBefore", label: "Сахар до", width: 56, align: "center" as const },
  { key: "glucoseAfter", label: "Сахар +2ч", width: 58, align: "center" as const },
  { key: "observedRatio", label: "УК", width: 56, align: "center" as const },
] as const;

function MealProfileSection({ rows }: { rows: MealProfileRow[] }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Профиль приёмов пищи</Text>
      <View style={styles.table}>
        <View style={[styles.tableRow, styles.tableHead, { height: HEAD_H }]}>
          {MEAL_COLS.map((col) => (
            <Cell key={col.key} align={col.align} text={col.label} width={col.width} />
          ))}
        </View>
        {rows.map((row) => (
          <View
            key={row.key}
            style={[
              styles.tableRow,
              { height: row.key === "total" ? TOTAL_H : ROW_H },
              ...(row.key === "total" ? [styles.totalRow] : []),
            ]}
          >
            {MEAL_COLS.map((col) => (
              <Cell
                key={col.key}
                align={col.align}
                strong={row.key === "total"}
                text={row[col.key as keyof MealProfileRow] as string}
                width={col.width}
              />
            ))}
          </View>
        ))}
      </View>
    </View>
  );
}

const DAILY_COLS = [
  { key: "dateLabel", label: "Дата", width: 50 },
  { key: "carbs", label: "Угл.", width: 44 },
  { key: "insulin", label: "Инс., ЕД", width: 52 },
  { key: "tir", label: "TIR", width: 40 },
  { key: "hypo", label: "Гипо", width: 38 },
  { key: "breakfast", label: "Завтрак", width: 62 },
  { key: "lunch", label: "Обед", width: 62 },
  { key: "dinner", label: "Ужин", width: 62 },
] as const;

function DailySection({
  medianRow,
  note,
  rows,
}: {
  medianRow: DailySummaryRow;
  note: string | null;
  rows: DailySummaryRow[];
}) {
  const maxRows = 6;
  const displayRows = rows.slice(0, maxRows);

  return (
    <View style={styles.section}>
      <View style={styles.sectionTitleRow}>
        <Text style={styles.sectionTitle}>Сводка по дням</Text>
        {note ? <Text style={styles.sectionNote}>{note}</Text> : null}
      </View>
      <View style={styles.table}>
        <View style={[styles.tableRow, styles.tableHead, { height: HEAD_H }]}>
          {DAILY_COLS.map((col) => (
            <Cell key={col.key} align="center" text={col.label} width={col.width} />
          ))}
        </View>
        {displayRows.map((row) => (
          <View
            key={row.date}
            style={[
              styles.tableRow,
              { height: ROW_H },
              ...(row.flagged ? [styles.flaggedRow] : []),
            ]}
          >
            {DAILY_COLS.map((col) => (
              <Cell
                key={col.key}
                align="center"
                text={row[col.key as keyof DailySummaryRow] as string}
                width={col.width}
              />
            ))}
          </View>
        ))}
        <View style={[styles.tableRow, styles.totalRow, { height: TOTAL_H }]}>
          {DAILY_COLS.map((col) => (
            <Cell
              key={col.key}
              align="center"
              strong
              text={medianRow[col.key as keyof DailySummaryRow] as string}
              width={col.width}
            />
          ))}
        </View>
      </View>
    </View>
  );
}

function BottomStrip({ metrics }: { metrics: ReportBottomMetric[] }) {
  const count = metrics.length || 1;
  const cellWidth = CONTENT_WIDTH / count;

  return (
    <View style={styles.bottomStrip}>
      {metrics.map((metric, i) => (
        <View
          key={metric.label}
          style={[
            styles.bottomCell,
            { width: cellWidth },
            ...(i === metrics.length - 1 ? [styles.bottomCellLast] : []),
          ]}
        >
          <Text style={styles.bottomLabel}>{metric.label}</Text>
          <View style={styles.bottomValueRow}>
            <Text style={styles.bottomValue}>{metric.value}</Text>
            {metric.unit ? <Text style={styles.bottomUnit}>{metric.unit}</Text> : null}
          </View>
        </View>
      ))}
    </View>
  );
}

function Cell({
  align = "left",
  strong = false,
  text,
  width,
}: {
  align?: "left" | "center" | "right";
  strong?: boolean;
  text: string;
  width: number;
}) {
  return (
    <Text
      style={[
        styles.cell,
        { textAlign: align, width },
        ...(strong ? [styles.strongCell] : []),
      ]}
    >
      {text}
    </Text>
  );
}

const c = {
  amberBg: "#FFF8EA",
  amberBorder: "#D9B77A",
  amberText: "#8A6330",
  border: "#D8D0C3",
  fill: "#F6F4EE",
  secondary: "#6F6A61",
  text: "#0A0A0A",
};

const styles = StyleSheet.create({
  appName: {
    color: c.secondary,
    fontFamily: "JetBrainsMono",
    fontSize: 9,
    letterSpacing: 0.2,
  },
  bottomCell: {
    borderRightColor: c.border,
    borderRightWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  bottomCellLast: {
    borderRightWidth: 0,
  },
  bottomLabel: {
    color: c.secondary,
    fontSize: 7,
    marginBottom: 2,
  },
  bottomStrip: {
    backgroundColor: c.fill,
    borderColor: c.border,
    borderWidth: 1,
    flexDirection: "row",
    marginTop: 10,
  },
  bottomUnit: {
    color: c.text,
    fontSize: 8,
    marginLeft: 3,
    paddingTop: 3,
  },
  bottomValue: {
    color: c.text,
    fontFamily: "JetBrainsMono",
    fontSize: 13,
  },
  bottomValueRow: {
    alignItems: "baseline",
    flexDirection: "row",
  },
  cell: {
    borderRightColor: c.border,
    borderRightWidth: 1,
    color: c.text,
    fontSize: TABLE_FONT,
    lineHeight: 1.15,
    paddingHorizontal: 4,
    paddingVertical: 0,
  },
  chip: {
    borderColor: c.border,
    borderWidth: 1,
    marginRight: 6,
    paddingHorizontal: 6,
    paddingVertical: 3,
  },
  chipText: {
    color: c.text,
    fontSize: 8,
  },
  chipsRow: {
    flexDirection: "row",
    marginBottom: 4,
    marginTop: 6,
  },
  flaggedRow: {
    backgroundColor: "#FFFDF7",
  },
  footer: {
    color: c.secondary,
    fontSize: 6.5,
    lineHeight: 1.25,
    marginTop: 8,
  },
  header: {
    marginBottom: 8,
  },
  headerRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 2,
  },
  kpiBlock: {
    marginBottom: 10,
  },
  kpiCaption: {
    color: c.secondary,
    fontSize: 6.5,
  },
  kpiCard: {
    borderColor: c.border,
    borderWidth: 1,
    height: KPI_CARD_HEIGHT,
    padding: 7,
    width: KPI_CARD_WIDTH,
  },
  kpiLabel: {
    color: c.text,
    fontFamily: "NotoSans",
    fontSize: 6.5,
    fontWeight: 700,
    letterSpacing: 0.4,
    marginBottom: 4,
  },
  kpiRow: {
    flexDirection: "row",
    gap: KPI_GAP,
  },
  kpiUnit: {
    color: c.text,
    fontSize: 8,
    marginLeft: 2,
    paddingTop: 7,
  },
  kpiValue: {
    color: c.text,
    fontFamily: "JetBrainsMono",
    fontSize: 22,
    letterSpacing: 0.2,
  },
  kpiValueRow: {
    alignItems: "baseline",
    flexDirection: "row",
    marginBottom: 2,
  },
  notes: {
    color: c.secondary,
    fontSize: 7,
    marginBottom: 4,
  },
  page: {
    backgroundColor: "#FFFFFF",
    fontFamily: "NotoSans",
    paddingHorizontal: MARGIN_X,
    paddingVertical: MARGIN_Y,
  },
  section: {
    marginTop: 10,
  },
  sectionNote: {
    color: c.secondary,
    fontSize: 7,
  },
  sectionTitle: {
    color: c.text,
    fontFamily: "NotoSans",
    fontSize: 10,
    fontWeight: 700,
    marginBottom: 4,
  },
  sectionTitleRow: {
    alignItems: "baseline",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  strongCell: {
    fontWeight: 700,
  },
  subtitle: {
    color: c.secondary,
    fontSize: 8,
  },
  table: {
    borderTopColor: c.border,
    borderTopWidth: 1,
  },
  tableHead: {
    backgroundColor: c.fill,
  },
  tableRow: {
    borderBottomColor: c.border,
    borderBottomWidth: 1,
    flexDirection: "row",
    minHeight: ROW_H,
  },
  title: {
    color: c.text,
    fontFamily: "NotoSans",
    fontSize: 18,
    fontWeight: 700,
    letterSpacing: -0.3,
    marginBottom: 2,
  },
  totalRow: {
    backgroundColor: c.fill,
  },
  warning: {
    alignItems: "center",
    backgroundColor: c.amberBg,
    borderColor: c.amberBorder,
    borderWidth: 1,
    flexDirection: "row",
    marginBottom: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  warningIcon: {
    borderColor: c.amberText,
    borderRadius: 6,
    borderWidth: 1,
    color: c.amberText,
    fontSize: 8,
    height: 12,
    marginRight: 8,
    textAlign: "center",
    width: 12,
  },
  warningText: {
    color: c.amberText,
    fontSize: 7.5,
  },
});
