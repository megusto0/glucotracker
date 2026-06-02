import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  FileText,
  Image,
  MoreVertical,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  Star,
  Trash2,
} from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import {
  apiClient,
  type AIRunResponse,
  type MealResponse,
  type ProductCreate,
  type ReestimateMealResponse,
} from "../../api/client";
import { FoodImage } from "../../components/FoodImage";
import { useBlobObjectUrl } from "../../components/useBlobObjectUrl";
import { Button } from "../../design/primitives/Button";
import { SectionLabel } from "../../design/primitives/SectionLabel";
import { Tag } from "../../design/primitives/Tag";
import { formatKcalValue, formatMacroValue, formatMmol, formatPercent } from "../../utils/nutritionFormat";
import { useApiConfig } from "../settings/settingsStore";

export const formatMealTime = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));

const twoDigits = (value: number) => value.toString().padStart(2, "0");

const mealDateTimeInputValue = (iso: string) => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return `${date.getFullYear()}-${twoDigits(date.getMonth() + 1)}-${twoDigits(
    date.getDate(),
  )}T${twoDigits(date.getHours())}:${twoDigits(date.getMinutes())}`;
};


const isoFromLocalDateTimeInput = (value: string) => {
  const [dateRaw, timeRaw] = value.split("T");
  const [yearRaw, monthRaw, dayRaw] = (dateRaw ?? "").split("-");
  const [hoursRaw, minutesRaw] = (timeRaw ?? "").split(":");
  const year = Number(yearRaw);
  const month = Number(monthRaw);
  const day = Number(dayRaw);
  const hours = Number(hoursRaw);
  const minutes = Number(minutesRaw);
  if (
    !Number.isInteger(year) ||
    !Number.isInteger(month) ||
    !Number.isInteger(day) ||
    !Number.isInteger(hours) ||
    !Number.isInteger(minutes) ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > 31 ||
    hours < 0 ||
    hours > 23 ||
    minutes < 0 ||
    minutes > 59
  ) {
    return null;
  }
  return `${year}-${twoDigits(month)}-${twoDigits(day)}T${twoDigits(
    hours,
  )}:${twoDigits(minutes)}:00`;
};

export const numberLabel = (value: number) => Math.round(value).toString();

const dailyMacroNorms = {
  carbs: 225,
  fat: 80,
  fiber: 30,
  protein: 120,
};

export const macroPercentsOfDailyNorm = (meal: MealResponse) => ({
  carbs: Math.round((meal.total_carbs_g / dailyMacroNorms.carbs) * 100),
  fat: Math.round((meal.total_fat_g / dailyMacroNorms.fat) * 100),
  fiber: Math.round((meal.total_fiber_g / dailyMacroNorms.fiber) * 100),
  protein: Math.round((meal.total_protein_g / dailyMacroNorms.protein) * 100),
});

type MealItem = NonNullable<MealResponse["items"]>[number];
type ReestimateModel =
  | "default"
  | "gemini-3-flash-preview"
  | "gemini-2.5-flash"
  | "gemini-3.1-flash-lite-preview";
type QuantityInfo = {
  quantity: number;
  badge: string;
  countLabel: string;
  packageBased: boolean;
  rowSubtitle: string;
  perUnitTitle: string;
  perUnitWeightG: number | null;
  totalWeightG: number | null;
  item: MealItem;
};

export const mealTitle = (meal: MealResponse) => {
  const itemNames =
    meal.items
      ?.slice(0, 3)
      .map((item) => item.name)
      .filter(Boolean) ?? [];

  let title = "";
  if (meal.status === "draft" && meal.source === "photo") {
    if (itemNames.length === 1) {
      title = itemNames[0];
    } else if (itemNames.length > 1) {
      title = `Еда по фото · ${meal.items?.length ?? itemNames.length} позиции`;
    }
  }

  title = title || meal.title || itemNames.join(" + ") || "Без названия";
  const quantity = mealQuantityInfo(meal);
  if (!quantity || title.includes("×")) {
    return title;
  }
  return `${title} ${quantity.badge}`;
};

const sourceLabels: Record<string, string> = {
  manual: "вручную",
  pattern: "шаблон",
  photo: "фото",
  mixed: "смешано",
};

const statusLabels: Record<string, string> = {
  accepted: "принято",
  draft: "черновик",
  discarded: "отменено",
};

const itemSourceKindLabels: Record<string, string> = {
  photo_estimate: "оценка по фото",
  label_calc: "рассчитано по этикетке",
  restaurant_db: "ресторанная база",
  product_db: "продуктовая база",
  pattern: "шаблон",
  manual: "вручную",
};

const calculationMethodLabels: Record<string, string> = {
  label_visible_weight_backend_calc: "Рассчитано по этикетке",
  label_assumed_weight_backend_calc: "Рассчитано по этикетке",
  label_split_visible_weight_backend_calc: "Рассчитано по этикетке",
  visual_estimate_gemini_mid: "Оценка по фото",
  manual_placeholder: "Вручную",
};

export const readableSource = (value?: string | null) =>
  value ? (sourceLabels[value] ?? value) : "";

export const readableStatus = (value?: string | null) =>
  value ? (statusLabels[value] ?? value) : "";

export const readableItemSourceKind = (value?: string | null) =>
  value ? (itemSourceKindLabels[value] ?? value) : "";

export const readableCalculationMethod = (value?: string | null) =>
  value ? (calculationMethodLabels[value] ?? value) : "";

const modelLabels: Record<string, string> = {
  default: "По умолчанию",
  "gemini-3-flash-preview": "Gemini 3 Flash",
  "gemini-2.5-flash": "Gemini 2.5 Flash",
  "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite",
};

const modelLabel = (value?: string | null) =>
  value ? (modelLabels[value] ?? value) : "неизвестно";

const signedMacro = (value: number, suffix: string) => {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatMacroValue(value)}${suffix}`;
};

const signedKcal = (value: number) => {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatKcalValue(value)} ккал`;
};

export const mealSourceText = (meal: MealResponse) =>
  `${readableSource(meal.source)} / ${readableStatus(meal.status)}`;

export const hasLowConfidence = (meal: MealResponse) =>
  (meal.confidence !== null &&
    meal.confidence !== undefined &&
    meal.confidence < 0.6) ||
  meal.items?.some(
    (item) =>
      item.confidence !== null &&
      item.confidence !== undefined &&
      item.confidence < 0.6,
  );

const itemImageUrl = (meal: MealResponse) =>
  meal.items?.find(
    (item) => item.image_url ?? item.source_image_url ?? item.image_cache_path,
  )?.image_url ??
  meal.items?.find((item) => item.source_image_url)?.source_image_url ??
  meal.items?.find((item) => item.image_cache_path)?.image_cache_path ??
  null;

const remoteMealThumbnail = (meal: MealResponse) => {
  const thumbnailUrl = meal.thumbnail_url;
  const sourceImage = itemImageUrl(meal);
  return sourceImage ?? thumbnailUrl ?? null;
};

type EvidenceCarrier = {
  evidence?: unknown;
  name?: string | null;
};

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const asNumber = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.replace(",", "."));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const postprandialChartPoints = (meal: MealResponse) => {
  const response = asRecord(meal.postprandial_response);
  const anchors = asRecord(response.anchors);
  return [0, 30, 60, 90, 180, 240, 300]
    .map((offset) => {
      const row = asRecord(anchors[String(offset)]);
      const value = asNumber(row.value ?? row.value_mmol_l);
      return value === null ? null : { offset, value };
    })
    .filter((point): point is { offset: number; value: number } => point !== null);
};

const parseQuantityFromServingText = (value?: string | null) => {
  if (!value) {
    return null;
  }
  const multiplier = value.match(/[×xх]\s*(\d+(?:[.,]\d+)?)/i);
  if (multiplier) {
    return asNumber(multiplier[1]);
  }
  const leading = value.match(/^(\d+(?:[.,]\d+)?)\s*(?:шт|упаков)/i);
  return leading ? asNumber(leading[1]) : null;
};

const isPackageQuantity = (item: MealItem, evidence: Record<string, unknown>) =>
  evidence.count_detected !== undefined ||
  item.calculation_method?.includes("label_split") ||
  /упаков/i.test(item.serving_text ?? "");

const unitWord = (quantity: number, packageBased: boolean) => {
  if (!packageBased) {
    return "шт";
  }
  const rounded = Math.round(quantity);
  if (rounded % 10 === 1 && rounded % 100 !== 11) {
    return "упаковка";
  }
  if ([2, 3, 4].includes(rounded % 10) && ![12, 13, 14].includes(rounded % 100)) {
    return "упаковки";
  }
  return "упаковок";
};

const quantityInfoForItem = (item: MealItem): QuantityInfo | null => {
  const evidence = asRecord(item.evidence);
  const quantity =
    asNumber(evidence.count_detected) ??
    asNumber(evidence.quantity) ??
    parseQuantityFromServingText(item.serving_text);
  if (!quantity || quantity <= 1) {
    return null;
  }

  const packageBased = isPackageQuantity(item, evidence);
  const perUnitWeightG =
    asNumber(evidence.net_weight_per_unit_g) ??
    (item.grams ? item.grams / quantity : null);
  const totalWeightG =
    asNumber(evidence.total_weight_g) ??
    item.grams ??
    (perUnitWeightG ? perUnitWeightG * quantity : null);
  const countLabel = `${formatMacroValue(quantity)} ${unitWord(
    quantity,
    packageBased,
  )}`;
  const rowSubtitle = perUnitWeightG
    ? `${countLabel} по ${formatMacroValue(perUnitWeightG)} г`
    : countLabel;

  return {
    quantity,
    badge: `×${formatMacroValue(quantity)}`,
    countLabel,
    packageBased,
    rowSubtitle,
    perUnitTitle: packageBased ? "На 1 упаковку" : "На 1 штуку",
    perUnitWeightG,
    totalWeightG,
    item,
  };
};

export const mealQuantityInfo = (meal: MealResponse): QuantityInfo | null =>
  meal.items?.map(quantityInfoForItem).find(Boolean) ?? null;

export const mealWeightLabel = (meal: MealResponse) => {
  const items = meal.items ?? [];
  if (!items.length) {
    return null;
  }
  if (items.length === 1) {
    const grams = items[0].grams;
    return grams !== null && grams !== undefined
      ? `${formatMacroValue(grams)} г`
      : null;
  }
  const gramsValues = items
    .map((item) => item.grams)
    .filter((grams): grams is number => typeof grams === "number");
  if (gramsValues.length !== items.length) {
    return null;
  }
  const total = gramsValues.reduce((sum, grams) => sum + grams, 0);
  return total > 0 ? `${formatMacroValue(total)} г всего` : null;
};

const roundedOneDecimal = (value: number | null | undefined) =>
  value === null || value === undefined ? null : Math.round(value * 10) / 10;

const roundedKcal = (value: number | null | undefined) =>
  value === null || value === undefined ? null : Math.round(value);

const per100Value = (servingValue: number | null, servingGrams: number | null) =>
  servingValue !== null && servingGrams !== null && servingGrams > 0
    ? roundedOneDecimal((servingValue * 100) / servingGrams)
    : null;

const stripQuantitySuffix = (value: string) =>
  value.replace(/\s*[xX×]\s*\d+(?:[.,]\d+)?\s*$/u, "").trim();

const uniqueAliases = (values: Array<string | null | undefined>) =>
  Array.from(
    new Set(
      values
        .map((value) => value?.trim())
        .filter((value): value is string => Boolean(value)),
    ),
  );

export const favoriteProductPayload = (
  meal: MealResponse,
  item: MealItem,
  quantity: QuantityInfo | null,
): ProductCreate => {
  const itemQuantity =
    quantity && quantity.item.id === item.id && quantity.quantity > 0
      ? quantity.quantity
      : 1;
  const servingGrams =
    quantity && quantity.item.id === item.id
      ? quantity.perUnitWeightG
      : item.grams ?? null;
  const servingCarbs = roundedOneDecimal(item.carbs_g / itemQuantity);
  const servingProtein = roundedOneDecimal(item.protein_g / itemQuantity);
  const servingFat = roundedOneDecimal(item.fat_g / itemQuantity);
  const servingFiber = roundedOneDecimal(item.fiber_g / itemQuantity);
  const servingKcal = roundedKcal(item.kcal / itemQuantity);
  const rawTitle = meal.title?.trim() || item.name;
  const name = stripQuantitySuffix(rawTitle) || item.name;

  return {
    aliases: uniqueAliases([name, item.name, meal.title]),
    barcode: null,
    brand: item.brand,
    carbs_per_100g: per100Value(servingCarbs, servingGrams),
    protein_per_100g: per100Value(servingProtein, servingGrams),
    fat_per_100g: per100Value(servingFat, servingGrams),
    fiber_per_100g: per100Value(servingFiber, servingGrams),
    kcal_per_100g: per100Value(servingKcal, servingGrams),
    carbs_per_serving: servingCarbs,
    protein_per_serving: servingProtein,
    fat_per_serving: servingFat,
    fiber_per_serving: servingFiber,
    kcal_per_serving: servingKcal,
    default_grams: servingGrams,
    default_serving_text: servingGrams
      ? `${formatMacroValue(servingGrams)} г`
      : item.serving_text,
    image_url: item.image_url ?? item.source_image_url ?? meal.thumbnail_url ?? null,
    name,
    nutrients_json: {},
    source_kind: "manual",
    source_url: null,
  };
};

const factBasisLabel = (basis: unknown) => {
  if (basis === "per_100g") {
    return "/ 100 г";
  }
  if (basis === "per_100ml") {
    return "/ 100 мл";
  }
  if (basis === "net_weight") {
    return "";
  }
  if (basis === "count") {
    return "";
  }
  return String(basis ?? "");
};

const formatVisibleFact = (fact: unknown) => {
  const row = asRecord(fact);
  const label = String(row.label_ru ?? "значение");
  const value =
    row.value === null || row.value === undefined
      ? "Значение неизвестно"
      : String(row.value);
  const unit = String(row.unit ?? "");
  const basis = factBasisLabel(row.basis);
  return [label, value, unit, basis].filter(Boolean).join(" ");
};

export const evidenceLabelsForItem = (item: EvidenceCarrier) => {
  const evidence = asRecord(item.evidence);
  const labels: string[] = [];
  if (Array.isArray(evidence.evidence_text)) {
    labels.push(...evidence.evidence_text.map((entry) => String(entry)));
  }
  if (Array.isArray(evidence.visible_label_facts)) {
    labels.push(...evidence.visible_label_facts.map(formatVisibleFact));
  }
  return labels.length ? labels : [item.name ?? "Данные позиции"];
};

const asRecordArray = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value) ? value.map(asRecord).filter((row) => row) : [];

const macroFields = [
  ["carbs_g", "У"],
  ["protein_g", "Б"],
  ["fat_g", "Ж"],
  ["fiber_g", "К"],
  ["kcal", "ккал"],
] as const;

const macroLine = (values: Record<string, unknown>) =>
  macroFields
    .map(([field, unit]) => {
      const value = asNumber(values[field]);
      if (value === null) {
        return null;
      }
      return `${field === "kcal" ? formatKcalValue(value) : formatMacroValue(value)}${unit}`;
    })
    .filter(Boolean)
    .join(" · ");

const knownComponentInfoForItem = (item?: MealItem | null) => {
  if (!item) {
    return null;
  }
  const evidence = asRecord(item.evidence);
  const componentEvidence = asRecord(
    evidence.known_component ?? evidence.carb_anchor,
  );
  const matches = asRecordArray(componentEvidence.matches);
  const componentEstimates = asRecordArray(evidence.component_estimates);
  const evidenceComponents = asRecordArray(componentEvidence.components);
  const knownCandidates = componentEstimates.filter(
    (component) =>
      component.component_type === "carb_base" ||
      component.type === "carb_anchor" ||
      component.type === "carb_base" ||
      component.component_type === "known_component" ||
      Boolean(component.should_use_database_if_available),
  );
  if (!matches.length && !knownCandidates.length && !evidenceComponents.length) {
    return null;
  }
  return {
    adjustedValues: asRecord(componentEvidence.final_backend_adjusted_values),
    rawModelValues: asRecord(componentEvidence.raw_model_estimate),
    componentRows: evidenceComponents.length
      ? evidenceComponents
      : knownCandidates.map((component) => ({
          name_ru: component.name_ru,
          component_type: component.component_type ?? component.type,
          estimated_grams_mid: component.estimated_grams_mid,
          raw_model_values: {
            carbs_g: component.carbs_g_mid,
            protein_g: component.protein_g_mid,
            fat_g: component.fat_g_mid,
            fiber_g: component.fiber_g_mid,
            kcal: component.kcal_mid,
          },
          final_values: {
            carbs_g: component.carbs_g_mid,
            protein_g: component.protein_g_mid,
            fat_g: component.fat_g_mid,
            fiber_g: component.fiber_g_mid,
            kcal: component.kcal_mid,
          },
          source: "gemini_visual_estimate",
          source_label: "фото-оценка",
        })),
    matches,
    knownCandidates,
  };
};

const defaultAnchorName = (component: Record<string, unknown>) => {
  const name = String(component.name_ru ?? "Компонент");
  const grams = asNumber(component.estimated_grams_mid);
  return grams ? `${name} ${formatMacroValue(grams)} г` : name;
};

const defaultAnchorAliases = (component: Record<string, unknown>) => {
  const values = [
    component.name_ru,
    component.likely_database_match_query,
    "тортилья",
    "лаваш",
    "wrap",
  ]
    .map((value) => String(value ?? "").trim())
    .filter(Boolean);
  return Array.from(new Set(values)).join(", ");
};

export function EmptyLog({ message }: { message: string }) {
  return (
    <div className="border-y border-[var(--hairline)] py-5 text-[15px] text-[var(--ink-3)]">
      {message}
    </div>
  );
}

export function MealRow({
  groupPosition = "single",
  meal,
  onToggle,
  selected,
  showTime = true,
}: {
  groupPosition?: "end" | "middle" | "single" | "start";
  meal: MealResponse;
  onToggle: () => void;
  selected: boolean;
  showTime?: boolean;
}) {
  const quantity = mealQuantityInfo(meal);
  const weightLabel = mealWeightLabel(meal);
  const cKcal = meal.total_carbs_g * 4;
  const pKcal = meal.total_protein_g * 4;
  const fKcal = meal.total_fat_g * 9;
  const macroTotal = cKcal + pKcal + fKcal || 1;
  const cPct = (cKcal / macroTotal) * 100;
  const pPct = (pKcal / macroTotal) * 100;
  const fPct = (fKcal / macroTotal) * 100;
  const metaParts = [
    readableSource(meal.source),
    readableStatus(meal.status),
    quantity?.rowSubtitle ?? weightLabel,
  ].filter(Boolean);
  const isGrouped = groupPosition !== "single";

  return (
    <div
      className={`meal clickable-row meal-card${selected ? " selected" : ""}${
        isGrouped ? ` meal-group-${groupPosition}` : ""
      }`}
      data-testid={`meal-row-${meal.id}`}
      onClick={onToggle}
      role="button"
      tabIndex={0}
    >
      <span className={`time ${showTime ? "" : "time-muted"}`}>
        {showTime ? formatMealTime(meal.eaten_at) : "↳"}
      </span>
      <MealThumbnail meal={meal} />
      <div className="meal-content">
        <div className="title">{mealTitle(meal)}</div>
        <div className="sub meal-meta-line">
          {metaParts.join(" / ")}
          {meal.nightscout_id || meal.nightscout_synced_at ? (
            <span className="tag" style={{ marginLeft: 4 }}>
              ns
            </span>
          ) : null}
          {hasLowConfidence(meal) ? (
            <span className="tag warn" style={{ marginLeft: 4 }}>
              проверить
            </span>
          ) : null}
        </div>
      </div>
      <div className="meal-macro-compact">
        <div className="meal-macro-main">
          {formatMacroValue(meal.total_carbs_g)} г угл ·{" "}
          {formatKcalValue(meal.total_kcal)} ккал
        </div>
        <div className="meal-macro-sub">
          <span>B {formatMacroValue(meal.total_protein_g)}</span>
          <span>F {formatMacroValue(meal.total_fat_g)}</span>
          <span>C {formatMacroValue(meal.total_carbs_g)}</span>
        </div>
        <div
          className="mp"
          title={`углеводы ${formatMacroValue(meal.total_carbs_g)}г · белки ${formatMacroValue(meal.total_protein_g)}г · жиры ${formatMacroValue(meal.total_fat_g)}г`}
        >
          <div className="mp-bar">
            <div
              style={{
                width: `${cPct}%`,
                height: "100%",
                background: "var(--accent)",
                float: "left",
              }}
            />
            <div
              style={{
                width: `${pPct}%`,
                height: "100%",
                background: "var(--ink)",
                float: "left",
              }}
            />
            <div
              style={{
                width: `${fPct}%`,
                height: "100%",
                background: "var(--ink-3)",
                float: "left",
              }}
            />
          </div>
        </div>
      </div>
      <button
        className="btn icon"
        style={{ border: "none", background: "transparent" }}
        onClick={(e) => e.stopPropagation()}
        type="button"
      >
        <MoreVertical size={14} strokeWidth={1.8} />
      </button>
    </div>
  );
}

function MealThumbnail({ meal }: { meal: MealResponse }) {
  const sourceImage = remoteMealThumbnail(meal);
  if (sourceImage) {
    return (
      <FoodImage
        alt={`${mealTitle(meal)} фото`}
        className="h-11 w-11"
        fit="contain"
        src={sourceImage}
      />
    );
  }

  const firstPhoto = meal.photos?.[0];
  if (firstPhoto) {
    return (
      <span className="h-11 w-11 overflow-hidden">
        <MealPhoto photo={firstPhoto} />
      </span>
    );
  }

  return (
    <FoodImage
      alt={`${mealTitle(meal)} фото`}
      className="h-11 w-11"
      fit="contain"
      src={null}
    />
  );
}

function PostprandialMiniChart({ meal }: { meal: MealResponse }) {
  const points = postprandialChartPoints(meal);
  const response = asRecord(meal.postprandial_response);
  if (points.length < 2 && Object.keys(response).length === 0) {
    return null;
  }
  const width = 236;
  const height = 70;
  const values = points.map((point) => point.value);
  const min = Math.min(...values, 4);
  const max = Math.max(...values, 10);
  const range = max - min || 1;
  const xFor = (offset: number) => (offset / 300) * width;
  const yFor = (value: number) => height - ((value - min) / range) * height;
  const path = points
    .map((point, index) => {
      const x = xFor(point.offset).toFixed(1);
      const y = yFor(point.value).toFixed(1);
      return `${index === 0 ? "M" : "L"}${x},${y}`;
    })
    .join(" ");
  const delta = asNumber(response.delta_max);
  const coverage = asNumber(response.coverage_180min);

  return (
    <section className="panel-section" data-testid="panel-postprandial">
      <div className="lbl">глюкоза после еды</div>
      <div className="row gap-8" style={{ alignItems: "center", marginTop: 8 }}>
        <svg
          aria-label="Мини-график глюкозы после еды"
          height={height}
          role="img"
          viewBox={`0 0 ${width} ${height}`}
          width={width}
        >
          <line x1="0" x2={width} y1={yFor(4)} y2={yFor(4)} stroke="var(--hairline-2)" strokeDasharray="3 3" />
          {path ? <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.5" /> : null}
          {points.map((point) => (
            <circle
              cx={xFor(point.offset)}
              cy={yFor(point.value)}
              fill="var(--surface)"
              key={point.offset}
              r="2.5"
              stroke="var(--accent)"
              strokeWidth="1.2"
            />
          ))}
        </svg>
        <div className="col gap-4" style={{ minWidth: 86 }}>
          <Tag>{delta !== null ? `+${formatMmol(delta)}` : "—"} ммоль/л</Tag>
          {coverage !== null ? <Tag>{formatPercent(coverage * 100)}% CGM</Tag> : null}
        </div>
      </div>
    </section>
  );
}

export function RightPanel({
  children,
  open,
}: {
  children: ReactNode;
  open: boolean;
}) {
  return (
    <aside
      className={`fixed right-0 top-0 z-40 h-screen w-[420px] border-l border-[var(--hairline)] bg-[var(--bg)] transition duration-200 ease-out ${
        open ? "translate-x-0 opacity-100" : "translate-x-full opacity-0"
      }`}
    >
      {children}
    </aside>
  );
}

function defaultProductAliases(item: MealItem | null) {
  if (!item) {
    return [];
  }
  const aliases = new Set<string>();
  aliases.add(item.name);
  aliases.add(item.name.toLocaleLowerCase("ru-RU"));
  if (item.brand) {
    aliases.add(`${item.brand} ${item.name}`);
  }
  const lowered = item.name.toLocaleLowerCase("ru-RU");
  if (lowered.includes("сырок")) {
    aliases.add("сырок");
    aliases.add("глазированный сырок");
    aliases.add("творожный сырок");
  }
  return Array.from(aliases).filter(Boolean);
}

function aliasesFromInput(value: string) {
  const aliases = value
    .split(",")
    .map((alias) => alias.trim())
    .filter(Boolean);
  return Array.from(new Set(aliases));
}

export function SelectedMealPanel({
  applyingReestimate = false,
  deletePending = false,
  meal,
  onDelete,
  onReestimate,
  onReestimateApply,
  onReestimateCancel,
  onReestimateModelChange,
  onRememberProduct,
  onCreateFromWeight,
  onUpdateItemWeight,
  onResyncNightscout,
  onSyncNightscout,
  onUpdateName,
  onUpdateTime,
  rememberPending = false,
  createFromWeightPending = false,
  updateWeightPending = false,
  reestimateComparison = null,
  reestimateError = null,
  reestimateModel = "gemini-3-flash-preview",
  reestimatePending = false,
  syncNightscoutPending = false,
  updateNamePending = false,
  updateTimePending = false,
}: {
  applyingReestimate?: boolean;
  discardPending?: boolean;
  duplicatePending?: boolean;
  deletePending?: boolean;
  meal: MealResponse;
  onDiscard?: (meal: MealResponse) => void;
  onDelete?: (meal: MealResponse) => void;
  onDuplicate?: (meal: MealResponse) => void;
  onReestimate?: () => void;
  onReestimateApply?: (
    mode: "replace_current" | "save_as_draft",
    comparison: ReestimateMealResponse,
  ) => void;
  onReestimateCancel?: () => void;
  onReestimateModelChange?: (model: ReestimateModel) => void;
  onRememberProduct?: (
    item: NonNullable<MealResponse["items"]>[number],
    aliases: string[],
  ) => void;
  onCreateFromWeight?: (item: MealItem, grams: number) => void;
  onUpdateItemWeight?: (item: MealItem, grams: number) => void;
  onResyncNightscout?: (meal: MealResponse) => void;
  onSave?: (meal: MealResponse) => void;
  onSyncNightscout?: (meal: MealResponse) => void;
  onUpdateName?: (meal: MealResponse, name: string) => void;
  onUpdateTime?: (meal: MealResponse, eatenAt: string) => void;
  rememberPending?: boolean;
  createFromWeightPending?: boolean;
  updateWeightPending?: boolean;
  reestimateComparison?: ReestimateMealResponse | null;
  reestimateError?: string | null;
  reestimateModel?: ReestimateModel;
  reestimatePending?: boolean;
  saveLabel?: string;
  syncNightscoutPending?: boolean;
  updateNamePending?: boolean;
  updateTimePending?: boolean;
}) {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  const firstPhoto = meal.photos?.[0];
  const imageUrl = remoteMealThumbnail(meal);
  const primaryItem = meal.items?.[0];
  const savedNameValue = meal.title?.trim() || primaryItem?.name?.trim() || "";
  const quantity = mealQuantityInfo(meal);
  const confidence =
    meal.confidence ??
    meal.items?.find((item) => item.confidence !== null)?.confidence ??
    null;
  const assumptions =
    meal.items?.flatMap((item) =>
      (item.assumptions ?? []).map((assumption) => String(assumption)),
    ) ?? [];
  const evidenceRows =
    meal.items?.flatMap((item) => evidenceLabelsForItem(item)) ?? [];
  const rememberableItem = useMemo(
    () =>
      meal.items?.find(
        (item) =>
          item.source_kind === "label_calc" ||
          item.calculation_method?.startsWith("label_"),
      ) ?? null,
    [meal.items],
  );
  const [aliasInput, setAliasInput] = useState(() =>
    defaultProductAliases(rememberableItem).join(", "),
  );
  useEffect(() => {
    setAliasInput(defaultProductAliases(rememberableItem).join(", "));
  }, [rememberableItem?.id]);
  const aiRuns = useQuery({
    queryKey: ["meal-ai-runs", meal.id, config.baseUrl, config.token],
    queryFn: () => apiClient.listMealAiRuns(config, meal.id),
    enabled: Boolean(config.token.trim() && meal.photos?.length),
  });
  const currentAiRun: AIRunResponse | undefined = aiRuns.data?.find(
    (run) => run.status === "success",
  );
  const currentModel =
    currentAiRun?.model_used ?? currentAiRun?.model ?? "неизвестно";
  const [nameValue, setNameValue] = useState(savedNameValue);
  const [nameError, setNameError] = useState<string | null>(null);
  const [dateTimeValue, setDateTimeValue] = useState(() =>
    mealDateTimeInputValue(meal.eaten_at),
  );
  const [dateTimeError, setDateTimeError] = useState<string | null>(null);
  const [editGrams, setEditGrams] = useState(() =>
    primaryItem?.grams ? String(primaryItem.grams) : "",
  );
  const [editGramsError, setEditGramsError] = useState<string | null>(null);
  const [repeatGrams, setRepeatGrams] = useState(() =>
    primaryItem?.grams ? "100" : "",
  );
  const [repeatError, setRepeatError] = useState<string | null>(null);
  useEffect(() => {
    setNameValue(savedNameValue);
    setNameError(null);
  }, [meal.id, savedNameValue]);
  useEffect(() => {
    setDateTimeValue(mealDateTimeInputValue(meal.eaten_at));
    setDateTimeError(null);
  }, [meal.id, meal.eaten_at]);
  useEffect(() => {
    setEditGrams(primaryItem?.grams ? String(primaryItem.grams) : "");
    setEditGramsError(null);
  }, [meal.id, primaryItem?.id, primaryItem?.grams]);
  useEffect(() => {
    setRepeatGrams(primaryItem?.grams ? "100" : "");
    setRepeatError(null);
  }, [meal.id, primaryItem?.id, primaryItem?.grams]);
  const nameChanged = nameValue.trim() !== savedNameValue;
  const savedDateTimeValue = mealDateTimeInputValue(meal.eaten_at);
  const dateTimeChanged = dateTimeValue !== savedDateTimeValue;
  const parsedEditGrams = asNumber(editGrams);
  const parsedRepeatGrams = asNumber(repeatGrams);
  const currentWeightLabel = mealWeightLabel(meal);
  const sourceSummary =
    readableItemSourceKind(primaryItem?.source_kind ?? meal.source) ||
    readableSource(meal.source) ||
    "источник неизвестен";
  const confidenceKind =
    confidence === null || confidence === undefined
      ? "нет данных"
      : confidence >= 0.8
        ? "высокая"
        : confidence >= 0.6
          ? "средняя"
          : "проверить";
  const ConfidenceIcon =
    confidence === null || confidence === undefined
      ? ShieldQuestion
      : confidence >= 0.8
        ? ShieldCheck
        : ShieldAlert;
  const confidenceSummary =
    confidence === null || confidence === undefined
      ? confidenceKind
      : `${confidenceKind} · ${formatPercent(confidence * 100)}%`;
  const macroSummary = `У ${formatMacroValue(meal.total_carbs_g)} г / Б ${formatMacroValue(
    meal.total_protein_g,
  )} г / Ж ${formatMacroValue(meal.total_fat_g)} г / К ${formatKcalValue(meal.total_kcal)} ккал`;
  const canEditWeight = Boolean(onUpdateItemWeight && primaryItem);
  const canRepeatByWeight = Boolean(onCreateFromWeight && primaryItem);
  const currentWeightChipValue =
    primaryItem?.grams && primaryItem.grams > 0 ? primaryItem.grams : null;
  const [favoriteProductId, setFavoriteProductId] = useState<string | null>(
    () => primaryItem?.product_id ?? null,
  );
  const favorite = Boolean(favoriteProductId);
  const [modelDetailsOpen, setModelDetailsOpen] = useState(false);
  const [componentsOpen, setComponentsOpen] = useState(false);
  const [assumptionsOpen, setAssumptionsOpen] = useState(false);
  const [rawDataOpen, setRawDataOpen] = useState(false);
  const [nightscoutOpen, setNightscoutOpen] = useState(false);
  const latestGlucose = useQuery({
    queryKey: ["panel-latest-glucose", config.baseUrl, config.token],
    queryFn: () => apiClient.getNightscoutLatestReading(config),
    enabled: Boolean(config.token.trim()),
    refetchInterval: 2 * 60 * 1000,
  });
  const favoriteProduct = useMutation({
    mutationFn: async () => {
      if (!primaryItem) {
        throw new Error("У записи нет позиции для сохранения в базу.");
      }
      if (favoriteProductId) {
        await apiClient.deleteProduct(config, favoriteProductId);
        return null;
      }

      const product = await apiClient.createProduct(
        config,
        favoriteProductPayload(meal, primaryItem, quantity),
      );
      await apiClient.updateMealItem(config, primaryItem.id, {
        product_id: product.id,
      });
      return product.id;
    },
    onSuccess: (productId) => {
      setFavoriteProductId(productId);
      [
        ["autocomplete"],
        ["database"],
        ["database-items"],
        ["feed-meals"],
        ["meals"],
        ["products"],
      ].forEach((queryKey) => {
        queryClient.invalidateQueries({ queryKey });
      });
    },
  });
  useEffect(() => {
    setFavoriteProductId(primaryItem?.product_id ?? null);
    setModelDetailsOpen(false);
    setComponentsOpen(false);
    setAssumptionsOpen(false);
    setRawDataOpen(false);
    setNightscoutOpen(false);
  }, [meal.id, primaryItem?.product_id]);
  const handleNameSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = nameValue.trim();
    if (!trimmedName) {
      setNameError("Введите название.");
      return;
    }
    setNameError(null);
    onUpdateName?.(meal, trimmedName);
  };
  const handleTimeSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextEatenAt = isoFromLocalDateTimeInput(dateTimeValue);
    if (!nextEatenAt) {
      setDateTimeError("Введите дату и время.");
      return;
    }
    setDateTimeError(null);
    onUpdateTime?.(meal, nextEatenAt);
  };
  const handleEditWeight = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!primaryItem || !onUpdateItemWeight) {
      return;
    }
    if (!parsedEditGrams || parsedEditGrams <= 0) {
      setEditGramsError("Введите вес больше 0 г.");
      return;
    }
    setEditGramsError(null);
    onUpdateItemWeight(primaryItem, parsedEditGrams);
  };
  const handleRepeatByWeight = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!primaryItem || !onCreateFromWeight) {
      return;
    }
    if (!parsedRepeatGrams || parsedRepeatGrams <= 0) {
      setRepeatError("Введите вес больше 0 г.");
      return;
    }
    setRepeatError(null);
    onCreateFromWeight(primaryItem, parsedRepeatGrams);
  };

  return (
    <div className="selected-panel">
      <div className="selected-panel-scroll">
        <section className="panel-headline panel-order-headline" data-testid="panel-headline">
          <div style={{ width: 56, height: 56, borderRadius: 3, overflow: "hidden", flexShrink: 0, border: "1px solid var(--hairline)", background: "var(--surface)" }}>
            {imageUrl ? (
              <FoodImage alt={`${mealTitle(meal)} фото`} fit="contain" src={imageUrl} />
            ) : firstPhoto ? (
              <MealPhoto photo={firstPhoto} />
            ) : (
              <div style={{ display: "flex", height: "100%", alignItems: "center", justifyContent: "center", color: "var(--ink-3)" }}>
                <Image size={20} strokeWidth={1.6} />
              </div>
            )}
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <h2>{mealTitle(meal)}</h2>
            <div className="panel-kcal-big">{formatKcalValue(meal.total_kcal)} ккал</div>
            <div className="row gap-4" style={{ marginTop: 8, flexWrap: "wrap" }}>
              <Tag>{readableSource(meal.source)}</Tag>
              <Tag>{readableStatus(meal.status)}</Tag>
              {currentWeightLabel ? <Tag>{currentWeightLabel}</Tag> : null}
              {quantity ? <Tag>{quantity.badge}</Tag> : null}
            </div>
          </div>
        </section>

        <section className="panel-summary panel-order-summary" data-testid="panel-summary">
          <div className="panel-summary-title">Сводка макросов</div>
          <div className="panel-summary-main panel-summary-one-line">
            <span>{macroSummary}</span>
          </div>
        </section>

        <PostprandialMiniChart meal={meal} />

        <section className="panel-section panel-order-edit" data-testid="panel-quick-edit">
          <div className="lbl">Быстрое редактирование</div>
          <form className="panel-quick-row" onSubmit={handleNameSubmit}>
            <label className="panel-input-label" htmlFor="meal-edit-name">Название</label>
            <input
              id="meal-edit-name"
              aria-label="Название"
              className="panel-input"
              disabled={!onUpdateName}
              onChange={(event) => setNameValue(event.target.value)}
              placeholder="Название еды"
              value={nameValue}
            />
            <button className="btn" disabled={!onUpdateName || !nameChanged || updateNamePending} type="submit">
              Сохранить
            </button>
          </form>
          {nameError ? <p style={{ fontSize: 12, color: "var(--warn)", marginTop: 6 }}>{nameError}</p> : null}
          <form className="panel-quick-row" onSubmit={handleTimeSubmit}>
            <label className="panel-input-label" htmlFor="meal-edit-time">Время</label>
            <input
              id="meal-edit-time"
              aria-label="Время"
              className="panel-input"
              disabled={!onUpdateTime}
              onChange={(event) => setDateTimeValue(event.target.value)}
              type="datetime-local"
              value={dateTimeValue}
            />
            <button className="btn" disabled={!onUpdateTime || !dateTimeChanged || updateTimePending} type="submit">
              Сохранить
            </button>
          </form>
          {dateTimeError ? <p style={{ fontSize: 12, color: "var(--warn)", marginTop: 6 }}>{dateTimeError}</p> : null}
          <form className="panel-quick-row" onSubmit={handleEditWeight}>
            <label className="panel-input-label" htmlFor="meal-edit-weight">Вес записи</label>
            <input
              id="meal-edit-weight"
              aria-label="Вес записи"
              className="panel-input"
              disabled={!canEditWeight}
              inputMode="decimal"
              onChange={(event) => setEditGrams(event.target.value)}
              placeholder="г"
              value={editGrams}
            />
            <button
              className="btn"
              disabled={updateWeightPending || !canEditWeight || !parsedEditGrams || parsedEditGrams <= 0}
              type="submit"
            >
              Сохранить
            </button>
          </form>
          {editGramsError ? <p style={{ fontSize: 12, color: "var(--warn)", marginTop: 6 }}>{editGramsError}</p> : null}
        </section>

        <section className="panel-section panel-order-edit panel-secondary-block panel-repeat-create" data-testid="panel-repeat-create">
          <div className="lbl">Создать ещё порцию</div>
          <p className="panel-helper-text">
            Создаст новую запись. Текущая не изменится.
          </p>
          <form className="panel-quick-row" onSubmit={handleRepeatByWeight}>
            <label className="panel-input-label" htmlFor="meal-repeat-weight">Граммы</label>
            <input
              id="meal-repeat-weight"
              aria-label="Граммы"
              className="panel-input"
              disabled={!canRepeatByWeight}
              inputMode="decimal"
              onChange={(event) => setRepeatGrams(event.target.value)}
              value={repeatGrams}
            />
            <button
              className="btn"
              disabled={createFromWeightPending || !canRepeatByWeight || !parsedRepeatGrams || parsedRepeatGrams <= 0}
              type="submit"
            >
              Создать
            </button>
          </form>
          <div className="panel-repeat-chips">
            {[
              { disabled: !canRepeatByWeight, label: "100 г", value: 100 },
              { disabled: !canRepeatByWeight, label: "127 г", value: 127 },
              {
                disabled: !canRepeatByWeight || currentWeightChipValue === null,
                label: "текущий вес",
                value: currentWeightChipValue ?? 100,
              },
            ].map((chip) => (
              <button
                className="btn"
                disabled={chip.disabled}
                key={chip.label}
                onClick={() => setRepeatGrams(String(chip.value))}
                type="button"
              >
                {chip.label}
              </button>
            ))}
          </div>
          {repeatError ? <p style={{ fontSize: 12, color: "var(--warn)", marginTop: 6 }}>{repeatError}</p> : null}
        </section>

        <section className="panel-section panel-source-block" data-testid="panel-source-confidence">
          <div className="lbl">Источник / достоверность</div>
          <div className="panel-source-confidence">
            <div>
              <div style={{ fontSize: 13, color: "var(--ink)" }}>{sourceSummary}</div>
              <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>
                {primaryItem?.serving_text ??
                  primaryItem?.brand ??
                  (readableCalculationMethod(primaryItem?.calculation_method) ||
                    readableSource(meal.source))}
              </div>
            </div>
            <div className="row gap-4" style={{ alignItems: "center" }}>
              <ConfidenceIcon size={14} />
              <Tag>{confidenceSummary}</Tag>
            </div>
          </div>
        </section>

        <section className="panel-section">
          <button aria-expanded={modelDetailsOpen} className="panel-accordion-btn" onClick={() => setModelDetailsOpen((prev) => !prev)} type="button">
            Оценка модели
            <ChevronDown className={modelDetailsOpen ? "rot-180" : ""} size={14} />
          </button>
          {modelDetailsOpen ? (
            <div className="panel-accordion-body">
              <div className="grid grid-cols-[1fr_auto] gap-3 text-[13px]">
                <span className="text-[var(--ink-3)]">Текущая оценка</span>
                <span className="text-right">{modelLabel(currentModel)}</span>
              </div>
              {onReestimate ? (
                <>
                  <label className="grid gap-2">
                    <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
                      Модель
                    </span>
                    <select
                      className="border border-[var(--hairline)] bg-[var(--surface)] px-3 py-2 text-[13px] outline-none"
                      onChange={(event) =>
                        onReestimateModelChange?.(event.target.value as ReestimateModel)
                      }
                      value={reestimateModel}
                    >
                      <option value="default">По умолчанию</option>
                      <option value="gemini-3-flash-preview">Gemini 3 Flash</option>
                      <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                      <option value="gemini-3.1-flash-lite-preview">
                        Gemini 3.1 Flash Lite
                      </option>
                    </select>
                  </label>
                  <Button
                    disabled={reestimatePending || !meal.photos?.length}
                    onClick={onReestimate}
                    variant="primary"
                  >
                    {reestimatePending ? "Переоцениваю фото..." : "Переоценить"}
                  </Button>
                  {reestimateComparison ? (
                    <ReestimateComparisonPanel
                      applying={applyingReestimate}
                      comparison={reestimateComparison}
                      onApply={onReestimateApply}
                      onCancel={onReestimateCancel}
                    />
                  ) : null}
                  {reestimateError ? (
                    <p className="text-[13px] text-[var(--warn)]">{reestimateError}</p>
                  ) : null}
                </>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="panel-section">
          <button aria-expanded={componentsOpen} className="panel-accordion-btn" onClick={() => setComponentsOpen((prev) => !prev)} type="button">
            Компоненты
            <ChevronDown className={componentsOpen ? "rot-180" : ""} size={14} />
          </button>
          {componentsOpen && primaryItem ? (
            <div className="panel-accordion-body">
              <KnownComponentSection item={primaryItem} />
            </div>
          ) : null}
        </section>

        <section className="panel-section">
          <button aria-expanded={assumptionsOpen} className="panel-accordion-btn" onClick={() => setAssumptionsOpen((prev) => !prev)} type="button">
            Допущения
            <ChevronDown className={assumptionsOpen ? "rot-180" : ""} size={14} />
          </button>
          {assumptionsOpen ? (
            <div className="panel-accordion-body">
              {assumptions.length ? (
                <ul className="grid gap-2 pl-5 text-[13px] text-[var(--ink)]">
                  {assumptions.slice(0, 4).map((assumption, index) => (
                    <li className="list-disc" key={`${assumption}-${index}`}>
                      {assumption}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[13px] text-[var(--ink-3)]">Допущений нет.</p>
              )}
            </div>
          ) : null}
        </section>

        <section className="panel-section">
          <button aria-expanded={rawDataOpen} className="panel-accordion-btn" onClick={() => setRawDataOpen((prev) => !prev)} type="button">
            Исходные данные
            <ChevronDown className={rawDataOpen ? "rot-180" : ""} size={14} />
          </button>
          {rawDataOpen ? (
            <div className="panel-accordion-body">
              {evidenceRows.length ? (
                evidenceRows
                  .slice(0, 6)
                  .map((label) => <EvidenceRow key={label} label={label} />)
              ) : (
                <>
                  <EvidenceRow label="Значения позиции" />
                  <EvidenceRow label="Источник и уверенность" />
                </>
              )}
              {quantity ? (
                <div className="grid gap-4" style={{ marginTop: 8 }}>
                  <NutritionBreakdownBlock
                    rows={[
                      ["углеводов", quantity.item.carbs_g / quantity.quantity, "г"],
                      ["белков", quantity.item.protein_g / quantity.quantity, "г"],
                      ["жиров", quantity.item.fat_g / quantity.quantity, "г"],
                      ["клетчатки", quantity.item.fiber_g / quantity.quantity, "г"],
                      ["ккал", quantity.item.kcal / quantity.quantity, "ккал"],
                    ]}
                    title={quantity.perUnitTitle}
                  />
                  <NutritionBreakdownBlock
                    rows={[
                      ["углеводов", meal.total_carbs_g, "г"],
                      ["белков", meal.total_protein_g, "г"],
                      ["жиров", meal.total_fat_g, "г"],
                      ["клетчатки", meal.total_fiber_g, "г"],
                      ["ккал", meal.total_kcal, "ккал"],
                    ]}
                    title="Итого"
                  />
                </div>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="panel-section">
          <button aria-expanded={nightscoutOpen} className="panel-accordion-btn" onClick={() => setNightscoutOpen((prev) => !prev)} type="button">
            Синхронизация Nightscout
            <ChevronDown className={nightscoutOpen ? "rot-180" : ""} size={14} />
          </button>
          {nightscoutOpen ? (
            <div className="panel-accordion-body">
              {meal.nightscout_id || meal.nightscout_synced_at ? (
                <div className="grid gap-1">
                  <span>Отправлено в Nightscout</span>
                  <span className="font-mono text-[12px] text-[var(--ink-3)]">
                    {meal.nightscout_synced_at
                      ? new Intl.DateTimeFormat("ru-RU", {
                          hour: "2-digit",
                          minute: "2-digit",
                        }).format(new Date(meal.nightscout_synced_at))
                      : meal.nightscout_id}
                  </span>
                </div>
              ) : meal.nightscout_sync_status === "failed" ? (
                <p className="text-[var(--warn)]">
                  ошибка NS: {meal.nightscout_sync_error ?? "не удалось отправить"}
                </p>
              ) : (
                <p className="text-[var(--ink-3)]">Запись ещё не отправлена.</p>
              )}
              {onSyncNightscout &&
              meal.status === "accepted" &&
              !meal.nightscout_id ? (
                <Button
                  disabled={syncNightscoutPending}
                  onClick={() => onSyncNightscout(meal)}
                >
                  {syncNightscoutPending ? "Отправляю..." : "Отправить в Nightscout"}
                </Button>
              ) : null}
              {onResyncNightscout &&
              meal.status === "accepted" &&
              meal.nightscout_id ? (
                <Button
                  disabled={syncNightscoutPending}
                  onClick={() => onResyncNightscout(meal)}
                >
                  {syncNightscoutPending
                    ? "Переотправляю..."
                    : "Переотправить в Nightscout"}
                </Button>
              ) : null}
              <p className="text-[12px] text-[var(--ink-3)]">
                Это запись дневника. Инсулин не отправляется и не рассчитывается.
              </p>
            </div>
          ) : null}
        </section>

      {rememberableItem && onRememberProduct ? (
        <section className="mt-6 border-t border-[var(--hairline)] pt-6">
          <h3 className="text-[13px] uppercase tracking-[0.02em]">продукт</h3>
          <p className="mt-3 text-[13px] text-[var(--ink-3)]">
            {rememberableItem.product_id
              ? "Позиция уже связана с базой продуктов. Можно добавить alias."
              : "Можно добавить в базу продуктов."}
          </p>
          <label className="mt-4 grid gap-2">
            <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
              alias
            </span>
            <input
              className="border border-[var(--hairline)] bg-[var(--surface)] px-3 py-2 text-[13px] outline-none focus:border-[var(--ink)]"
              onChange={(event) => setAliasInput(event.target.value)}
              placeholder="сырок, глазированный сырок"
              value={aliasInput}
            />
          </label>
          <Button
            disabled={rememberPending}
            onClick={() =>
              onRememberProduct(rememberableItem, aliasesFromInput(aliasInput))
            }
            variant="primary"
          >
            Запомнить продукт
          </Button>
        </section>
      ) : null}
      </div>

      <div className="selected-panel-actions" data-testid="panel-actions">
        <div className="row gap-8" style={{ flexWrap: "wrap" }}>
          <Button
            disabled={favoriteProduct.isPending || !primaryItem}
            icon={<Star size={15} />}
            onClick={() => favoriteProduct.mutate()}
            variant={favorite ? "primary" : "quiet"}
          >
            {favorite ? "В избранном" : "В избранное"}
          </Button>
          {onDelete ? (
            <Button
              disabled={deletePending}
              icon={<Trash2 size={15} />}
              onClick={() => onDelete(meal)}
              variant="danger"
            >
              Удалить
            </Button>
          ) : null}
        </div>
      </div>

      <div className="selected-panel-glucose" data-testid="panel-sticky-glucose">
        <SectionLabel className="mb-2">Глюкоза</SectionLabel>
        <div className="row" style={{ alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>последнее значение</span>
          <a className="btn-link" href="/glucose">Открыть</a>
        </div>
        <div style={{ marginTop: 6, fontSize: 13, color: "var(--ink)" }}>
          {latestGlucose.isLoading
            ? "Обновляю…"
            : latestGlucose.data?.value_mmol_l !== null &&
                latestGlucose.data?.value_mmol_l !== undefined
              ? `${formatMmol(latestGlucose.data.value_mmol_l)} ммоль/л`
              : "нет данных"}
        </div>
      </div>
    </div>
  );
}

function KnownComponentSection({ item }: { item: MealItem }) {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  const info = knownComponentInfoForItem(item);
  const component = info?.knownCandidates[0] ?? {};
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState(() => defaultAnchorName(component));
  const [grams, setGrams] = useState(() =>
    asNumber(component.estimated_grams_mid)?.toString() ?? "",
  );
  const [carbs, setCarbs] = useState("");
  const [protein, setProtein] = useState("");
  const [fat, setFat] = useState("");
  const [fiber, setFiber] = useState("");
  const [kcal, setKcal] = useState("");
  const [aliases, setAliases] = useState(() => defaultAnchorAliases(component));

  useEffect(() => {
    setName(defaultAnchorName(component));
    setGrams(asNumber(component.estimated_grams_mid)?.toString() ?? "");
    setAliases(defaultAnchorAliases(component));
    setCarbs("");
    setProtein("");
    setFat("");
    setFiber("");
    setKcal("");
    setFormOpen(false);
  }, [item.id]);

  const createComponent = useMutation({
    mutationFn: async () => {
      const parsedCarbs = asNumber(carbs);
      const parsedProtein = asNumber(protein);
      const parsedFat = asNumber(fat);
      const parsedFiber = asNumber(fiber);
      const parsedKcal = asNumber(kcal);
      if (
        parsedCarbs === null &&
        parsedProtein === null &&
        parsedFat === null &&
        parsedFiber === null &&
        parsedKcal === null
      ) {
        throw new Error("Введите хотя бы одно значение компонента.");
      }
      const parsedGrams = asNumber(grams);
      const payload: ProductCreate = {
        barcode: null,
        brand: null,
        name: name.trim() || "Компонент",
        default_grams: parsedGrams,
        default_serving_text: parsedGrams ? `${formatMacroValue(parsedGrams)} г` : "1 шт",
        carbs_per_100g: null,
        protein_per_100g: null,
        fat_per_100g: null,
        fiber_per_100g: null,
        kcal_per_100g: null,
        carbs_per_serving: parsedCarbs,
        protein_per_serving: parsedProtein,
        fat_per_serving: parsedFat,
        fiber_per_serving: parsedFiber,
        kcal_per_serving: parsedKcal,
        source_kind: "personal_component",
        source_url: null,
        image_url: null,
        nutrients_json: {},
        aliases: aliasesFromInput(aliases),
      };
      const product = await apiClient.createProduct(config, payload);
      const existingEvidence = asRecord(item.evidence);
      const manualOverride = {
        grams_g: parsedGrams,
        name: payload.name,
        source: "manual_override",
        carbs_g: parsedCarbs,
        protein_g: parsedProtein,
        fat_g: parsedFat,
        fiber_g: parsedFiber,
        kcal: parsedKcal,
      };
      await apiClient.updateMealItem(config, item.id, {
        ...(parsedCarbs !== null ? { carbs_g: parsedCarbs } : {}),
        ...(parsedProtein !== null ? { protein_g: parsedProtein } : {}),
        ...(parsedFat !== null ? { fat_g: parsedFat } : {}),
        ...(parsedFiber !== null ? { fiber_g: parsedFiber } : {}),
        ...(parsedKcal !== null ? { kcal: parsedKcal } : {}),
        calculation_method: "manual_known_component_override",
        evidence: {
          ...existingEvidence,
          manual_overrides: {
            ...asRecord(existingEvidence.manual_overrides),
            known_component: manualOverride,
          },
        },
        assumptions: [
          ...(Array.isArray(item.assumptions) ? item.assumptions : []),
          `Исправлено вручную и сохранено как компонент: ${payload.name}.`,
        ],
      });
      return product;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["autocomplete"] });
      queryClient.invalidateQueries({ queryKey: ["database"] });
      queryClient.invalidateQueries({ queryKey: ["database-items"] });
      queryClient.invalidateQueries({ queryKey: ["meals"] });
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      setFormOpen(false);
    },
  });

  if (!info) {
    return null;
  }

  return (
    <section className="mt-6 border-b border-[var(--hairline)] pb-6">
      <h3 className="text-[13px] uppercase tracking-[0.02em]">
        Компоненты
      </h3>
      {info.matches.length ? (
        <div className="mt-4 grid gap-3">
          {info.componentRows.map((rowInput, index) => {
            const row = asRecord(rowInput);
            const finalValues = asRecord(row.final_values);
            const rawValues = asRecord(row.raw_model_values);
            return (
              <div
                className="border-y border-[var(--hairline)] py-3"
                key={`${String(row.matched_component_id ?? row.name_ru)}-${index}`}
              >
                <div className="text-[15px] text-[var(--ink)]">
                  {String(row.matched_component_name ?? row.name_ru ?? "Компонент")}
                </div>
                <div className="mt-2 font-mono text-[18px]">
                  {macroLine(finalValues) || "значение неизвестно"}
                </div>
                <div className="mt-2 text-[12px] text-[var(--ink-3)]">
                  {String(row.source_label ?? "фото-оценка")}
                  {macroLine(rawValues)
                    ? ` · оценка модели: ${macroLine(rawValues)}`
                    : ""}
                </div>
              </div>
            );
          })}
          <div className="grid grid-cols-2 gap-3 text-[12px]">
            <div>
              <div className="uppercase tracking-[0.06em] text-[var(--ink-3)]">
                Оценка модели
              </div>
              <div className="mt-1 font-mono text-[18px]">
                {macroLine(info.rawModelValues) || "неизвестно"}
              </div>
            </div>
            <div>
              <div className="uppercase tracking-[0.06em] text-[var(--ink-3)]">
                Итог после корректировки
              </div>
              <div className="mt-1 font-mono text-[18px]">
                {macroLine(info.adjustedValues) || "неизвестно"}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-4 grid gap-3">
          <p className="text-[13px] text-[var(--warn)]">
            Углеводная основа не найдена в базе. Значение оценено визуально.
          </p>
          {info.knownCandidates.map((row, index) => (
            <div className="border-b border-[var(--hairline)] py-2" key={index}>
              <div className="text-[15px]">{String(row.name_ru ?? "Компонент")}</div>
              <div className="mt-1 text-[12px] text-[var(--ink-3)]">
                Gemini оценил массу:{" "}
                {asNumber(row.estimated_grams_mid) !== null
                  ? `${formatMacroValue(asNumber(row.estimated_grams_mid) ?? 0)} г`
                  : "неизвестно"}
              </div>
            </div>
          ))}
          {!formOpen ? (
            <Button onClick={() => setFormOpen(true)}>Исправить вручную</Button>
          ) : (
            <div className="grid gap-3 border border-[var(--hairline)] p-3">
              <label className="grid gap-1 text-[12px]">
                Название
                <input
                  className="border border-[var(--hairline)] bg-[var(--surface)] px-2 py-2 text-[13px] outline-none"
                  onChange={(event) => setName(event.target.value)}
                  value={name}
                />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="grid gap-1 text-[12px]">
                  Масса, г
                  <input
                    className="border border-[var(--hairline)] bg-[var(--surface)] px-2 py-2 font-mono text-[13px] outline-none"
                    onChange={(event) => setGrams(event.target.value)}
                    value={grams}
                  />
                </label>
                <label className="grid gap-1 text-[12px]">
                  Углеводы, г
                  <input
                    className="border border-[var(--hairline)] bg-[var(--surface)] px-2 py-2 font-mono text-[13px] outline-none"
                    onChange={(event) => setCarbs(event.target.value)}
                    placeholder="24"
                    value={carbs}
                  />
                </label>
                <label className="grid gap-1 text-[12px]">
                  Белки, г
                  <input
                    className="border border-[var(--hairline)] bg-[var(--surface)] px-2 py-2 font-mono text-[13px] outline-none"
                    onChange={(event) => setProtein(event.target.value)}
                    placeholder="4"
                    value={protein}
                  />
                </label>
                <label className="grid gap-1 text-[12px]">
                  Жиры, г
                  <input
                    className="border border-[var(--hairline)] bg-[var(--surface)] px-2 py-2 font-mono text-[13px] outline-none"
                    onChange={(event) => setFat(event.target.value)}
                    placeholder="4"
                    value={fat}
                  />
                </label>
                <label className="grid gap-1 text-[12px]">
                  Клетчатка, г
                  <input
                    className="border border-[var(--hairline)] bg-[var(--surface)] px-2 py-2 font-mono text-[13px] outline-none"
                    onChange={(event) => setFiber(event.target.value)}
                    value={fiber}
                  />
                </label>
                <label className="grid gap-1 text-[12px]">
                  Ккал
                  <input
                    className="border border-[var(--hairline)] bg-[var(--surface)] px-2 py-2 font-mono text-[13px] outline-none"
                    onChange={(event) => setKcal(event.target.value)}
                    placeholder="150"
                    value={kcal}
                  />
                </label>
              </div>
              <label className="grid gap-1 text-[12px]">
                Алиасы
                <input
                  className="border border-[var(--hairline)] bg-[var(--surface)] px-2 py-2 text-[13px] outline-none"
                  onChange={(event) => setAliases(event.target.value)}
                  value={aliases}
                />
              </label>
              {createComponent.isError ? (
                <p className="text-[12px] text-[var(--warn)]">
                  {(createComponent.error as Error).message}
                </p>
              ) : null}
              <Button
                disabled={createComponent.isPending}
                onClick={() => createComponent.mutate()}
                variant="primary"
              >
                Сохранить как компонент
              </Button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function ReestimateComparisonPanel({
  applying,
  comparison,
  onApply,
  onCancel,
}: {
  applying: boolean;
  comparison: ReestimateMealResponse;
  onApply?: (
    mode: "replace_current" | "save_as_draft",
    comparison: ReestimateMealResponse,
  ) => void;
  onCancel?: () => void;
}) {
  const delta = comparison.diff.totals;
  const itemCountChanged =
    comparison.current_items.length !== comparison.proposed_items.length;
  return (
    <div className="grid gap-4 border-b border-[var(--hairline)] py-5">
      <h4 className="text-[12px] uppercase tracking-[0.06em]">
        Сравнение оценок
      </h4>
      {comparison.fallback_used ? (
        <p className="border border-[var(--hairline)] px-3 py-2 text-[12px] text-[var(--accent)]">
          Использована запасная модель
        </p>
      ) : null}
      <div className="grid grid-cols-2 gap-3">
        <ComparisonTotals
          label="Текущая"
          model={comparison.diff.current_model}
          totals={comparison.current_totals}
        />
        <ComparisonTotals
          label="Новая"
          model={comparison.model_used}
          totals={comparison.proposed_totals}
        />
      </div>
      <div className="border-y border-[var(--hairline)] py-3">
        <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
          Разница
        </div>
        <div className="mt-2 font-mono text-[15px]">
          {signedMacro(delta.carbs_delta, "У")} ·{" "}
          {signedMacro(delta.protein_delta, "Б")} ·{" "}
          {signedMacro(delta.fat_delta, "Ж")} · {signedKcal(delta.kcal_delta)}
        </div>
      </div>
      {itemCountChanged ? (
        <p className="text-[13px] text-[var(--warn)]">
          Новая модель иначе определила позиции. Проверьте перед сохранением.
        </p>
      ) : null}
      {(comparison.diff.warnings ?? []).map((warning) => (
        <p className="text-[13px] text-[var(--warn)]" key={warning}>
          {warning}
        </p>
      ))}
      <div className="grid grid-cols-2 gap-3 text-[13px]">
        <ItemList title="Текущая версия" items={comparison.current_items} />
        <ItemList title="Новая оценка" items={comparison.proposed_items} />
      </div>
      <div className="grid gap-2">
        <Button
          disabled={applying}
          onClick={() => onApply?.("replace_current", comparison)}
          variant="primary"
        >
          Заменить новой
        </Button>
        <Button
          disabled={applying}
          onClick={() => onApply?.("save_as_draft", comparison)}
        >
          Сохранить как черновик
        </Button>
        <Button disabled={applying} onClick={onCancel}>
          Оставить текущую
        </Button>
      </div>
    </div>
  );
}

function ComparisonTotals({
  label,
  model,
  totals,
}: {
  label: string;
  model?: string | null;
  totals: ReestimateMealResponse["current_totals"];
}) {
  return (
    <div className="border border-[var(--hairline)] p-3">
      <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
        {label}
      </div>
      <div className="mt-2 text-[12px] text-[var(--ink)]">
        {modelLabel(model)}
      </div>
      <div className="mt-3 font-mono text-[13px]">
        {formatMacroValue(totals.total_carbs_g)}У ·{" "}
        {formatMacroValue(totals.total_protein_g)}Б ·{" "}
        {formatMacroValue(totals.total_fat_g)}Ж
      </div>
      <div className="mt-1 font-mono text-[18px]">
        {formatKcalValue(totals.total_kcal)} ккал
      </div>
    </div>
  );
}

function ItemList({
  items,
  title,
}: {
  items: ReestimateMealResponse["current_items"];
  title: string;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
        {title}
      </div>
      <ol className="mt-2 grid gap-1">
        {items.map((item, index) => (
          <li className="truncate" key={`${title}-${item.name}-${index}`}>
            {index + 1}. {item.name}
          </li>
        ))}
      </ol>
    </div>
  );
}

function EvidenceRow({ label }: { label: string }) {
  return (
    <div className="grid grid-cols-[24px_1fr] items-center gap-3 py-1">
      <FileText size={16} strokeWidth={1.7} />
      <span className="text-[13px] text-[var(--ink)]">{label}</span>
    </div>
  );
}

function NutritionBreakdownBlock({
  rows,
  title,
}: {
  rows: Array<[string, number, "г" | "ккал"]>;
  title: string;
}) {
  return (
    <div>
      <h3 className="text-[13px] uppercase tracking-[0.02em]">{title}</h3>
      <div className="mt-3 grid gap-2">
        {rows.map(([label, value, unit]) => (
          <div
            className="grid grid-cols-[80px_1fr] border-b border-[var(--hairline)] py-2"
            key={`${title}-${label}`}
          >
            <span className="font-mono text-[18px] text-[var(--ink)]">
              {unit === "ккал" ? formatKcalValue(value) : formatMacroValue(value)}
              <span className="ml-1 text-[11px] text-[var(--ink-3)]">{unit}</span>
            </span>
            <span className="self-end text-[13px] text-[var(--ink-3)]">
              {label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MealPhoto({
  photo,
}: {
  photo: NonNullable<MealResponse["photos"]>[number];
}) {
  const config = useApiConfig();
  const photoFile = useQuery({
    queryKey: ["photo-file", photo.id, config.baseUrl, config.token],
    queryFn: () => apiClient.getPhotoFile(config, photo.id),
    enabled: Boolean(config.token.trim()),
  });
  const photoObjectUrl = useBlobObjectUrl(photoFile.data);

  return (
    <div className="h-full w-full overflow-hidden bg-[var(--surface)]">
      {photoObjectUrl ? (
        <img
          alt={photo.original_filename ?? "фото еды"}
          className="h-full w-full object-cover"
          src={photoObjectUrl}
        />
      ) : (
        <div className="flex h-full items-end p-3">
          <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
            {photoFile.isError
              ? "фото недоступно"
              : (photo.original_filename ?? "фото прикреплено")}
          </span>
        </div>
      )}
    </div>
  );
}
