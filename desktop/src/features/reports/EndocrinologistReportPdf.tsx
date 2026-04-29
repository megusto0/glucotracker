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
      <Page size="A4" style={styles.page}>
        <View style={styles.paper}>
          <Header data={data} />
          <KpiGrid items={data.kpis} />
          <MealProfileTable rows={data.mealProfileRows} />
          <DailyTable
            medianRow={data.dailyMedianRow}
            note={data.dailyRowsNote}
            rows={data.shownDailyRows}
          />
          <BottomStrip metrics={data.bottomMetrics} />
          <Text style={styles.footer}>{data.footer}</Text>
        </View>
      </Page>
    </Document>
  );
}

function Header({ data }: { data: EndocrinologistReportData }) {
  return (
    <View>
      <Text style={styles.appName}>{data.appName}</Text>
      <Text style={styles.title}>{data.title}</Text>
      <Text style={styles.subtitle}>
        {data.periodLabel} · {data.generatedLabel}
      </Text>
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

function KpiGrid({ items }: { items: ReportKpi[] }) {
  return (
    <View style={styles.kpiGrid}>
      {items.map((item) => (
        <View key={item.label} style={styles.kpiCard}>
          <Text style={styles.kpiLabel}>{item.label}</Text>
          <View style={styles.kpiValueRow}>
            <Text style={styles.kpiValue}>{item.value}</Text>
            {item.unit ? <Text style={styles.kpiUnit}>{item.unit}</Text> : null}
          </View>
          <Text style={styles.kpiCaption}>{item.caption}</Text>
        </View>
      ))}
    </View>
  );
}

function MealProfileTable({ rows }: { rows: MealProfileRow[] }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Профиль приёмов пищи</Text>
      <View style={styles.table}>
        <View style={[styles.tableRow, styles.tableHead]}>
          <TableCell text="Приём пищи" width={108} />
          <TableCell align="center" text="Эпизодов" width={64} />
          <TableCell align="center" text="Угл., г" width={56} />
          <TableCell align="center" text="Инсулин, ЕД" width={74} />
          <TableCell align="center" text="Сахар до" width={67} />
          <TableCell align="center" text="Сахар +2ч" width={72} />
          <TableCell align="center" text="УК" width={72} />
        </View>
        {rows.map((row) => (
          <View
            key={row.key}
            style={
              row.key === "total"
                ? [styles.tableRow, styles.totalRow]
                : styles.tableRow
            }
          >
            <TableCell strong={row.key === "total"} text={row.label} width={108} />
            <TableCell align="center" text={row.episodes} width={64} />
            <TableCell align="center" text={row.carbs} width={56} />
            <TableCell align="center" text={row.insulin} width={74} />
            <TableCell align="center" text={row.glucoseBefore} width={67} />
            <TableCell align="center" text={row.glucoseAfter} width={72} />
            <TableCell align="center" text={row.observedRatio} width={72} />
          </View>
        ))}
      </View>
    </View>
  );
}

function DailyTable({
  medianRow,
  note,
  rows,
}: {
  medianRow: DailySummaryRow;
  note: string | null;
  rows: DailySummaryRow[];
}) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionTitleRow}>
        <Text style={styles.sectionTitle}>Сводка по дням</Text>
        {note ? <Text style={styles.sectionNote}>{note}</Text> : null}
      </View>
      <View style={styles.table}>
        <View style={[styles.tableRow, styles.tableHead]}>
          <TableCell align="center" text="Дата" width={56} />
          <TableCell align="center" text="Угл., г" width={58} />
          <TableCell align="center" text="Инсулин, ЕД" width={74} />
          <TableCell align="center" text="TIR" width={58} />
          <TableCell align="center" text="Гипо" width={52} />
          <TableCell align="center" text="Завтрак" width={72} />
          <TableCell align="center" text="Обед" width={72} />
          <TableCell align="center" text="Ужин" width={72} />
        </View>
        {rows.map((row) => (
          <DailyRow key={row.date} row={row} />
        ))}
        <DailyRow median row={medianRow} />
      </View>
    </View>
  );
}

function DailyRow({ median = false, row }: { median?: boolean; row: DailySummaryRow }) {
  return (
    <View
      style={[
        styles.tableRow,
        ...(median ? [styles.totalRow] : []),
        ...(row.flagged ? [styles.flaggedRow] : []),
      ]}
    >
      <TableCell align="center" strong={median} text={row.dateLabel} width={56} />
      <TableCell align="center" text={row.carbs} width={58} />
      <TableCell align="center" text={row.insulin} width={74} />
      <TableCell align="center" text={row.tir} width={58} />
      <TableCell align="center" text={row.hypo} width={52} />
      <TableCell align="center" text={row.breakfast} width={72} />
      <TableCell align="center" text={row.lunch} width={72} />
      <TableCell align="center" text={row.dinner} width={72} />
    </View>
  );
}

function BottomStrip({ metrics }: { metrics: ReportBottomMetric[] }) {
  return (
    <View style={styles.bottomStrip}>
      {metrics.map((metric, index) => (
        <View
          key={metric.label}
          style={[
            styles.bottomMetric,
            ...(index === metrics.length - 1 ? [styles.bottomMetricLast] : []),
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

function TableCell({
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
        styles.tableCell,
        { textAlign: align, width },
        ...(strong ? [styles.strongCell] : []),
      ]}
    >
      {text}
    </Text>
  );
}

const colors = {
  amberBg: "#FFF8EA",
  amberBorder: "#D9B77A",
  amberText: "#8A6330",
  border: "#D8D0C3",
  fill: "#F6F4EE",
  paper: "#FFFFFF",
  secondary: "#6F6A61",
  text: "#0A0A0A",
};

const styles = StyleSheet.create({
  appName: {
    color: colors.text,
    fontFamily: "JetBrainsMono",
    fontSize: 14,
    letterSpacing: 0.2,
    marginBottom: 10,
  },
  bottomLabel: {
    color: colors.secondary,
    fontSize: 8,
    marginBottom: 2,
  },
  bottomMetric: {
    borderRightColor: colors.border,
    borderRightWidth: 1,
    flexGrow: 1,
    minHeight: 44,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  bottomMetricLast: {
    borderRightWidth: 0,
    flexGrow: 1.6,
  },
  bottomStrip: {
    backgroundColor: colors.fill,
    borderColor: colors.border,
    borderRadius: 5,
    borderWidth: 1,
    flexDirection: "row",
    marginTop: 12,
  },
  bottomUnit: {
    color: colors.text,
    fontSize: 9,
    marginLeft: 4,
    paddingTop: 5,
  },
  bottomValue: {
    color: colors.text,
    fontFamily: "JetBrainsMono",
    fontSize: 17,
  },
  bottomValueRow: {
    alignItems: "baseline",
    flexDirection: "row",
  },
  chip: {
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    marginRight: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  chipText: {
    color: colors.text,
    fontSize: 9,
  },
  chipsRow: {
    flexDirection: "row",
    marginBottom: 10,
    marginTop: 12,
  },
  flaggedRow: {
    backgroundColor: "#FFFDF7",
  },
  footer: {
    color: colors.secondary,
    fontSize: 8.8,
    lineHeight: 1.35,
    marginTop: 12,
  },
  kpiCaption: {
    color: colors.secondary,
    fontSize: 8.5,
  },
  kpiCard: {
    borderColor: colors.border,
    borderRadius: 4,
    borderWidth: 1,
    height: 75,
    marginBottom: 6,
    marginRight: 6,
    padding: 10,
    width: 126.5,
  },
  kpiGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginBottom: 10,
  },
  kpiLabel: {
    color: colors.text,
    fontFamily: "NotoSans",
    fontSize: 8.8,
    fontWeight: 700,
    letterSpacing: 1.1,
    marginBottom: 6,
  },
  kpiUnit: {
    color: colors.text,
    fontSize: 12,
    marginLeft: 5,
    paddingTop: 15,
  },
  kpiValue: {
    color: colors.text,
    fontFamily: "JetBrainsMono",
    fontSize: 30,
    letterSpacing: 0.3,
  },
  kpiValueRow: {
    alignItems: "baseline",
    flexDirection: "row",
    marginBottom: 3,
  },
  notes: {
    color: colors.secondary,
    fontSize: 8,
    marginBottom: 6,
  },
  page: {
    backgroundColor: "#EFECE5",
    fontFamily: "NotoSans",
    padding: 10,
  },
  paper: {
    backgroundColor: colors.paper,
    borderColor: colors.border,
    borderWidth: 1,
    height: "100%",
    paddingHorizontal: 25,
    paddingVertical: 22,
  },
  section: {
    marginTop: 7,
  },
  sectionNote: {
    color: colors.secondary,
    fontSize: 8,
  },
  sectionTitle: {
    color: colors.text,
    fontFamily: "NotoSans",
    fontSize: 13,
    fontWeight: 700,
    marginBottom: 6,
  },
  sectionTitleRow: {
    alignItems: "baseline",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  strongCell: {
    fontWeight: 700,
  },
  subtitle: {
    color: colors.secondary,
    fontSize: 10.5,
    marginTop: 4,
  },
  table: {
    borderTopColor: colors.border,
    borderTopWidth: 1,
  },
  tableCell: {
    borderRightColor: colors.border,
    borderRightWidth: 1,
    color: colors.text,
    fontSize: 8.6,
    lineHeight: 1.2,
    paddingHorizontal: 6,
    paddingVertical: 5,
  },
  tableHead: {
    backgroundColor: colors.fill,
  },
  tableRow: {
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    flexDirection: "row",
    minHeight: 23,
  },
  title: {
    color: colors.text,
    fontFamily: "NotoSans",
    fontSize: 27,
    fontWeight: 700,
    letterSpacing: -0.5,
  },
  totalRow: {
    backgroundColor: colors.fill,
  },
  warning: {
    alignItems: "center",
    backgroundColor: colors.amberBg,
    borderColor: colors.amberBorder,
    borderRadius: 3,
    borderWidth: 1,
    flexDirection: "row",
    marginBottom: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  warningIcon: {
    borderColor: colors.amberText,
    borderRadius: 8,
    borderWidth: 1,
    color: colors.amberText,
    fontSize: 10,
    height: 16,
    marginRight: 10,
    textAlign: "center",
    width: 16,
  },
  warningText: {
    color: colors.amberText,
    fontSize: 10,
  },
});
