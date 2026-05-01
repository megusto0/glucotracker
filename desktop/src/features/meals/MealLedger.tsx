import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, FileText, Image, MoreVertical, Trash2 } from "lucide-react";
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
import { formatKcalValue, formatMacroValue } from "../../utils/nutritionFormat";
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

const mealDateLabel = (iso: string) =>
  new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(iso));

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
      return `${formatMacroValue(value)}${unit}`;
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
    <div className="border-y border-[var(--hairline)] py-5 text-[15px] text-[var(--muted)]">
      {message}
    </div>
  );
}

export function MealRow({
  meal,
  onToggle,
  selected,
}: {
  meal: MealResponse;
  onToggle: () => void;
  selected: boolean;
}) {
  const quantity = mealQuantityInfo(meal);
  const weightLabel = mealWeightLabel(meal);
  return (
    <article
      className={`border-b border-[var(--hairline)] ${
        selected ? "bg-[var(--surface)]" : ""
      }`}
    >
      <button
        className="grid w-full grid-cols-[72px_44px_minmax(240px,1fr)_1fr_72px_72px_72px_112px_24px] items-center gap-4 py-3 text-left"
        onClick={onToggle}
        type="button"
      >
        <span className="font-mono text-[13px] text-[var(--fg)]">
          {formatMealTime(meal.eaten_at)}
        </span>
        <MealThumbnail meal={meal} />
        <span className="grid min-w-0 gap-1">
          <span className="truncate text-[15px] text-[var(--fg)]">
            {mealTitle(meal)}
          </span>
          <span className="flex items-center gap-2 text-[10px] uppercase tracking-[0.06em] text-[var(--muted)]">
            <span>
              {mealSourceText(meal)}
              {quantity
                ? ` · ${quantity.rowSubtitle}`
                : weightLabel
                  ? ` · ${weightLabel}`
                  : ""}
            </span>
            {quantity ? <TinyLabel>{quantity.badge}</TinyLabel> : null}
            {meal.status === "draft" ? <TinyLabel>черновик</TinyLabel> : null}
            {meal.nightscout_id || meal.nightscout_synced_at ? (
              <TinyLabel>ns</TinyLabel>
            ) : null}
            {hasLowConfidence(meal) ? <TinyLabel>проверить</TinyLabel> : null}
          </span>
        </span>
        <span className="h-px border-b border-dotted border-[var(--hairline)]" />
        <span className="text-right font-mono text-[18px]">
          {numberLabel(meal.total_carbs_g)}
          <span className="ml-0.5 text-[11px] text-[var(--muted)]">У</span>
        </span>
        <span className="text-right font-mono text-[16px]">
          {numberLabel(meal.total_protein_g)}
          <span className="ml-0.5 text-[10px] text-[var(--muted)]">Б</span>
        </span>
        <span className="text-right font-mono text-[16px]">
          {numberLabel(meal.total_fat_g)}
          <span className="ml-0.5 text-[10px] text-[var(--muted)]">Ж</span>
        </span>
        <span className="text-right font-mono text-[18px]">
          {numberLabel(meal.total_kcal)}
          <span className="ml-1 text-[11px] text-[var(--muted)]">ккал</span>
        </span>
        <span className="flex justify-end text-[var(--fg)]">
          <MoreVertical size={16} strokeWidth={1.8} />
        </span>
      </button>
    </article>
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

function TinyLabel({ children }: { children: string }) {
  return (
    <span className="border border-[var(--hairline)] px-1 py-0.5 text-[10px] uppercase tracking-[0.06em] text-[var(--muted)]">
      {children}
    </span>
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
  discardPending = false,
  duplicatePending = false,
  deletePending = false,
  meal,
  onDiscard,
  onDelete,
  onDuplicate,
  onReestimate,
  onReestimateApply,
  onReestimateCancel,
  onReestimateModelChange,
  onRememberProduct,
  onCreateFromWeight,
  onUpdateItemWeight,
  onResyncNightscout,
  onSave,
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
  saveLabel = "Сохранить",
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
  const firstPhoto = meal.photos?.[0];
  const imageUrl = remoteMealThumbnail(meal);
  const primaryItem = meal.items?.[0];
  const savedNameValue = meal.title?.trim() || primaryItem?.name?.trim() || "";
  const quantity = mealQuantityInfo(meal);
  const macros = [
    ["углеводы", meal.total_carbs_g, "г"],
    ["белки", meal.total_protein_g, "г"],
    ["жиры", meal.total_fat_g, "г"],
    ["клетчатка", meal.total_fiber_g, "г"],
  ] as const;
  const confidence =
    meal.confidence ??
    meal.items?.find((item) => item.confidence !== null)?.confidence ??
    null;
  const confidenceLabel =
    confidence === null || confidence === undefined
      ? "--"
      : confidence.toFixed(2);
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
  const canEditWeight = Boolean(
    onUpdateItemWeight &&
      primaryItem &&
      primaryItem.grams !== null &&
      primaryItem.grams !== undefined &&
      primaryItem.grams > 0,
  );
  const editWeightChanged = Boolean(
    primaryItem &&
      parsedEditGrams !== null &&
      primaryItem.grams !== null &&
      primaryItem.grams !== undefined &&
      Math.abs(parsedEditGrams - primaryItem.grams) > 0.001,
  );
  const canRepeatByWeight = Boolean(
    onCreateFromWeight &&
      primaryItem &&
      primaryItem.grams !== null &&
      primaryItem.grams !== undefined &&
      primaryItem.grams > 0,
  );
  const unitRepeatWeight =
    quantity?.perUnitWeightG && quantity.perUnitWeightG > 0
      ? quantity.perUnitWeightG
      : null;
  const quickRepeatUnitLabel = quantity?.packageBased ? "упаковку" : "шт";
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
  const handleQuickRepeatByWeight = (grams: number) => {
    if (!primaryItem || !onCreateFromWeight || grams <= 0) {
      return;
    }
    setRepeatError(null);
    setRepeatGrams(String(grams));
    onCreateFromWeight(primaryItem, grams);
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto px-7 py-8">
      <div className="grid grid-cols-[96px_1fr_auto] gap-4">
        <div className="h-24 w-24 overflow-hidden border border-[var(--hairline)] bg-[var(--surface)]">
          {imageUrl ? (
            <FoodImage
              alt={`${mealTitle(meal)} фото`}
              className="h-full w-full border-0"
              fit="contain"
              src={imageUrl}
            />
          ) : firstPhoto ? (
            <MealPhoto photo={firstPhoto} />
          ) : (
            <div className="flex h-full items-center justify-center text-[var(--muted)]">
              <Image size={24} strokeWidth={1.6} />
            </div>
          )}
        </div>
        <div className="min-w-0">
          <h2 className="text-[24px] leading-tight text-[var(--fg)]">
            {mealTitle(meal)}
          </h2>
          <p className="mt-2 text-[13px] text-[var(--fg)]">
            {primaryItem?.brand ?? readableSource(meal.source)}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <SourceTag>{readableSource(meal.source)}</SourceTag>
            <SourceTag>{readableStatus(meal.status)}</SourceTag>
            {currentWeightLabel ? <SourceTag>{currentWeightLabel}</SourceTag> : null}
            {quantity ? <SourceTag>{quantity.badge}</SourceTag> : null}
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-[30px] leading-none">
            {numberLabel(meal.total_kcal)}
          </div>
          <div className="mt-1 text-[12px] text-[var(--fg)]">ккал</div>
        </div>
      </div>

      {onUpdateName ? (
        <form
          className="mt-6 grid gap-3 border-y border-[var(--hairline)] py-4"
          onSubmit={handleNameSubmit}
        >
          <label className="grid gap-2">
            <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
              Название
            </span>
            <input
              aria-label="Название записи"
              className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent text-[22px] leading-none text-[var(--fg)] outline-none focus:border-[var(--fg)]"
              onChange={(event) => setNameValue(event.target.value)}
              placeholder="Название еды"
              value={nameValue}
            />
          </label>
          <div className="flex items-center justify-between gap-3">
            <span className="text-[12px] text-[var(--muted)]">
              {meal.items?.length === 1 && primaryItem?.product_id
                ? "Обновит название записи, позиции и продукта в базе."
                : meal.items?.length === 1 && rememberableItem
                  ? "Обновит название записи, позиции и продукта в базе, если он сохранён или может быть сохранён."
                : meal.items?.length === 1
                  ? "Обновит название записи и позиции."
                  : "Обновит название записи."}
            </span>
            <Button
              disabled={!nameChanged || updateNamePending}
              type="submit"
              variant="primary"
            >
              {updateNamePending ? "Сохраняю..." : "Сохранить название"}
            </Button>
          </div>
          {nameError ? (
            <p className="text-[13px] text-[var(--danger)]">{nameError}</p>
          ) : null}
        </form>
      ) : null}

      {onUpdateTime ? (
        <form
          className="mt-6 grid gap-3 border-y border-[var(--hairline)] py-4"
          onSubmit={handleTimeSubmit}
        >
          <div className="grid grid-cols-[1fr_auto] items-end gap-3">
            <label className="grid gap-2">
              <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                Дата и время записи
              </span>
              <input
                aria-label="Дата и время записи"
                className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent font-mono text-[22px] leading-none text-[var(--fg)] outline-none focus:border-[var(--fg)]"
                onChange={(event) => setDateTimeValue(event.target.value)}
                type="datetime-local"
                value={dateTimeValue}
              />
            </label>
            <Button
              disabled={!dateTimeChanged || updateTimePending}
              type="submit"
              variant="primary"
            >
              {updateTimePending ? "Сохраняю..." : "Сохранить дату"}
            </Button>
          </div>
          <div className="grid grid-cols-[1fr_auto] gap-3 text-[12px] text-[var(--muted)]">
            <span>{mealDateLabel(meal.eaten_at)}</span>
            <span>текущее: {savedDateTimeValue.replace("T", " ")}</span>
          </div>
          <p className="text-[12px] text-[var(--muted)]">
            Если изменить день, запись переместится в журнал этого дня.
          </p>
          {dateTimeError ? (
            <p className="text-[13px] text-[var(--danger)]">{dateTimeError}</p>
          ) : null}
        </form>
      ) : null}

      {quantity ? (
        <section className="mt-6 border-y border-[var(--hairline)] py-5">
          <h3 className="text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
            Количество
          </h3>
          <div className="mt-3 font-mono text-[34px] leading-none text-[var(--fg)]">
            {quantity.countLabel}
          </div>
          <p className="mt-3 text-[13px] text-[var(--muted)]">
            {quantity.perUnitWeightG
              ? `${formatMacroValue(quantity.quantity)} × ${formatMacroValue(
                  quantity.perUnitWeightG,
                )} г`
              : quantity.countLabel}
            {quantity.totalWeightG
              ? ` · ${formatMacroValue(quantity.totalWeightG)} г всего`
              : ""}
          </p>
        </section>
      ) : null}

      {canEditWeight ? (
        <form
          className="mt-6 grid gap-3 border-y border-[var(--hairline)] py-4"
          onSubmit={handleEditWeight}
        >
          <div className="grid gap-2">
            <h3 className="text-[13px] uppercase tracking-[0.02em]">
              Вес текущей записи
            </h3>
            <p className="text-[12px] text-[var(--muted)]">
              Изменит эту запись. Backend пересчитает углеводы, ккал и макросы
              пропорционально весу.
            </p>
          </div>
          <div className="grid grid-cols-[1fr_auto] items-end gap-3">
            <label className="grid gap-2">
              <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                вес текущей записи, г
              </span>
              <input
                aria-label="Вес текущей записи, г"
                className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent font-mono text-[28px] leading-none text-[var(--fg)] outline-none focus:border-[var(--fg)]"
                inputMode="decimal"
                onChange={(event) => setEditGrams(event.target.value)}
                value={editGrams}
              />
            </label>
            <Button
              disabled={
                updateWeightPending ||
                !editWeightChanged ||
                !parsedEditGrams ||
                parsedEditGrams <= 0
              }
              type="submit"
              variant="primary"
            >
              {updateWeightPending ? "Сохраняю..." : "Сохранить вес"}
            </Button>
          </div>
          {editGramsError ? (
            <p className="text-[13px] text-[var(--danger)]">{editGramsError}</p>
          ) : null}
        </form>
      ) : null}

      {canRepeatByWeight ? (
        <form
          className="mt-6 grid gap-3 border-y border-[var(--hairline)] py-4"
          onSubmit={handleRepeatByWeight}
        >
          <div className="grid gap-2">
            <h3 className="text-[13px] uppercase tracking-[0.02em]">
              Повтор по весу
            </h3>
            <p className="text-[12px] text-[var(--muted)]">
              Основа: {formatMacroValue(primaryItem?.grams ?? 0)} г. Backend
              пересчитает значения на новый вес и создаст запись сейчас.
            </p>
          </div>
          {unitRepeatWeight ? (
            <div className="grid gap-2 border border-[var(--hairline)] bg-[var(--surface)] p-3">
              <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                Быстро из распознанного количества
              </div>
              <button
                className="flex items-center justify-between gap-3 text-left transition hover:text-[var(--fg)] disabled:cursor-not-allowed disabled:text-[var(--muted)]"
                disabled={createFromWeightPending}
                onClick={() => handleQuickRepeatByWeight(unitRepeatWeight)}
                type="button"
              >
                <span className="text-[14px] text-[var(--fg)]">
                  Добавить 1 {quickRepeatUnitLabel}
                </span>
                <span className="font-mono text-[16px]">
                  {formatMacroValue(unitRepeatWeight)} г
                </span>
              </button>
            </div>
          ) : null}
          <div className="grid grid-cols-[1fr_auto] items-end gap-3">
            <label className="grid gap-2">
              <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                вес новой записи, г
              </span>
              <input
                aria-label="Вес новой записи, г"
                className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent font-mono text-[28px] leading-none text-[var(--fg)] outline-none focus:border-[var(--fg)]"
                inputMode="decimal"
                onChange={(event) => setRepeatGrams(event.target.value)}
                value={repeatGrams}
              />
            </label>
            <Button
              disabled={
                createFromWeightPending ||
                !parsedRepeatGrams ||
                parsedRepeatGrams <= 0
              }
              type="submit"
              variant="primary"
            >
              {createFromWeightPending
                ? "Добавляю..."
                : `Добавить ${formatMacroValue(parsedRepeatGrams ?? 100)} г`}
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {[unitRepeatWeight ?? 0, 100, 127, primaryItem?.grams ?? 0]
              .filter((grams, index, values) => grams > 0 && values.indexOf(grams) === index)
              .map((grams) => (
                <button
                  className="border border-[var(--hairline)] bg-[var(--surface)] px-3 py-1.5 text-[12px] text-[var(--muted)] transition hover:text-[var(--fg)]"
                  key={grams}
                  onClick={() => setRepeatGrams(String(grams))}
                  type="button"
                >
                  {formatMacroValue(grams)} г
                </button>
              ))}
          </div>
          {repeatError ? (
            <p className="text-[13px] text-[var(--danger)]">{repeatError}</p>
          ) : null}
        </form>
      ) : null}

      <div className="mt-8 grid grid-cols-4 border-b border-[var(--hairline)] pb-6">
        {macros.map(([label, value, unit]) => (
          <div className="text-center" key={label}>
            <div className="font-mono text-[24px] leading-none">
              {numberLabel(value)}
            </div>
            <div className="mt-2 text-[11px] uppercase tracking-[0.02em]">
              {label}{" "}
              <span className="lowercase text-[var(--muted)]">{unit}</span>
            </div>
          </div>
        ))}
      </div>

      <section className="mt-6 grid grid-cols-2 gap-3 border-b border-[var(--hairline)] pb-6">
        <InfoBlock title="Источник">
          <div className="text-[15px] text-[var(--fg)]">
            {readableItemSourceKind(primaryItem?.source_kind ?? meal.source)}
          </div>
          <div className="mt-2 text-[12px] text-[var(--muted)]">
            {primaryItem?.serving_text ??
              primaryItem?.brand ??
              (readableCalculationMethod(primaryItem?.calculation_method) ||
                readableSource(meal.source))}
          </div>
        </InfoBlock>
        <InfoBlock title="Уверенность">
          <div className="font-mono text-[28px] leading-none text-[var(--fg)]">
            {confidenceLabel}
          </div>
          <div className="mt-2 text-[12px] text-[var(--muted)]">
            {confidence !== null &&
            confidence !== undefined &&
            confidence >= 0.8
              ? "высокая"
              : confidence !== null &&
                  confidence !== undefined &&
                  confidence >= 0.6
                ? "средняя"
                : confidence === null || confidence === undefined
                  ? "нет данных"
                  : "проверить"}
          </div>
        </InfoBlock>
      </section>

      <section className="mt-6 border-b border-[var(--hairline)] pb-6">
        <h3 className="text-[13px] uppercase tracking-[0.02em]">Nightscout</h3>
        <div className="mt-3 grid gap-3 text-[13px] text-[var(--fg)]">
          {meal.nightscout_id || meal.nightscout_synced_at ? (
            <div className="grid gap-1">
              <span>Отправлено в Nightscout</span>
              <span className="font-mono text-[12px] text-[var(--muted)]">
                {meal.nightscout_synced_at
                  ? new Intl.DateTimeFormat("ru-RU", {
                      hour: "2-digit",
                      minute: "2-digit",
                    }).format(new Date(meal.nightscout_synced_at))
                  : meal.nightscout_id}
              </span>
            </div>
          ) : meal.nightscout_sync_status === "failed" ? (
            <p className="text-[var(--danger)]">
              ошибка NS: {meal.nightscout_sync_error ?? "не удалось отправить"}
            </p>
          ) : (
            <p className="text-[var(--muted)]">Запись ещё не отправлена.</p>
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
          <p className="text-[12px] text-[var(--muted)]">
            Это запись дневника. Инсулин не отправляется и не рассчитывается.
          </p>
        </div>
      </section>

      {primaryItem ? <KnownComponentSection item={primaryItem} /> : null}

      <section className="mt-6 border-b border-[var(--hairline)] pb-6">
        <h3 className="text-[13px] uppercase tracking-[0.02em]">Допущения</h3>
        {assumptions.length ? (
          <ul className="mt-3 grid gap-2 pl-5 text-[13px] text-[var(--fg)]">
            {assumptions.slice(0, 4).map((assumption, index) => (
              <li className="list-disc" key={`${assumption}-${index}`}>
                {assumption}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-[13px] text-[var(--muted)]">Допущений нет.</p>
        )}
      </section>

      <section className="mt-6 border-b border-[var(--hairline)] pb-6">
        <h3 className="text-[13px] uppercase tracking-[0.02em]">Данные</h3>
        <div className="mt-4 grid gap-2">
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
        </div>
      </section>

      {quantity ? (
        <section className="mt-5 grid gap-4 border-b border-[var(--hairline)] pb-6">
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
        </section>
      ) : (
        <section className="mt-5 grid gap-3">
          <h3 className="text-[13px] uppercase tracking-[0.02em]">Итого</h3>
          <div className="grid grid-cols-4 gap-4 py-4 text-center">
            <TotalMetric label="ккал" value={meal.total_kcal} />
            <TotalMetric label="углеводы г" value={meal.total_carbs_g} />
            <TotalMetric label="белки г" value={meal.total_protein_g} />
            <TotalMetric label="жиры г" value={meal.total_fat_g} />
          </div>
        </section>
      )}

      {onReestimate ? (
        <section className="mt-6 border-t border-[var(--hairline)] pt-6">
          <h3 className="text-[13px] uppercase tracking-[0.02em]">
            Модель оценки
          </h3>
          <div className="mt-4 grid gap-3 border-b border-[var(--hairline)] pb-4">
            <div className="grid grid-cols-[1fr_auto] gap-3 text-[13px]">
              <span className="text-[var(--muted)]">Текущая оценка</span>
              <span className="text-right">{modelLabel(currentModel)}</span>
            </div>
            <div className="font-mono text-[15px] text-[var(--fg)]">
              {formatMacroValue(meal.total_carbs_g)}У ·{" "}
              {formatMacroValue(meal.total_protein_g)}Б ·{" "}
              {formatMacroValue(meal.total_fat_g)}Ж ·{" "}
              {formatKcalValue(meal.total_kcal)} ккал
            </div>
            <label className="grid gap-2">
              <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
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
            {!meal.photos?.length ? (
              <p className="text-[12px] text-[var(--muted)]">
                У этой записи нет фото для переоценки
              </p>
            ) : null}
            {reestimateError ? (
              <p className="text-[13px] text-[var(--danger)]">
                {reestimateError}
              </p>
            ) : null}
          </div>

          {reestimateComparison ? (
            <ReestimateComparisonPanel
              applying={applyingReestimate}
              comparison={reestimateComparison}
              onApply={onReestimateApply}
              onCancel={onReestimateCancel}
            />
          ) : null}
        </section>
      ) : null}

      {rememberableItem && onRememberProduct ? (
        <section className="mt-6 border-t border-[var(--hairline)] pt-6">
          <h3 className="text-[13px] uppercase tracking-[0.02em]">продукт</h3>
          <p className="mt-3 text-[13px] text-[var(--muted)]">
            {rememberableItem.product_id
              ? "Позиция уже связана с базой продуктов. Можно добавить alias."
              : "Можно добавить в базу продуктов."}
          </p>
          <label className="mt-4 grid gap-2">
            <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
              alias
            </span>
            <input
              className="border border-[var(--hairline)] bg-[var(--surface)] px-3 py-2 text-[13px] outline-none focus:border-[var(--fg)]"
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

      <div className="sticky bottom-0 mt-auto grid gap-3 border-t border-[var(--hairline)] bg-[var(--bg)] py-4">
        {onSave ? (
          <Button onClick={() => onSave(meal)} variant="primary">
            {saveLabel}
          </Button>
        ) : null}
        {onDiscard ? (
          <Button
            disabled={discardPending}
            onClick={() => onDiscard(meal)}
            variant="danger"
          >
            Отменить
          </Button>
        ) : null}
        {onDuplicate ? (
          <Button
            disabled={duplicatePending}
            icon={<Copy size={15} />}
            onClick={() => onDuplicate(meal)}
          >
            Повторить
          </Button>
        ) : null}
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
        <p className="pt-5 text-[11px] text-[var(--muted)]">
          Это оценка, не медицинская рекомендация.
        </p>
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
                <div className="text-[15px] text-[var(--fg)]">
                  {String(row.matched_component_name ?? row.name_ru ?? "Компонент")}
                </div>
                <div className="mt-2 font-mono text-[18px]">
                  {macroLine(finalValues) || "значение неизвестно"}
                </div>
                <div className="mt-2 text-[12px] text-[var(--muted)]">
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
              <div className="uppercase tracking-[0.06em] text-[var(--muted)]">
                Оценка модели
              </div>
              <div className="mt-1 font-mono text-[18px]">
                {macroLine(info.rawModelValues) || "неизвестно"}
              </div>
            </div>
            <div>
              <div className="uppercase tracking-[0.06em] text-[var(--muted)]">
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
          <p className="text-[13px] text-[var(--danger)]">
            Углеводная основа не найдена в базе. Значение оценено визуально.
          </p>
          {info.knownCandidates.map((row, index) => (
            <div className="border-b border-[var(--hairline)] py-2" key={index}>
              <div className="text-[15px]">{String(row.name_ru ?? "Компонент")}</div>
              <div className="mt-1 text-[12px] text-[var(--muted)]">
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
                <p className="text-[12px] text-[var(--danger)]">
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
        <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          Разница
        </div>
        <div className="mt-2 font-mono text-[15px]">
          {signedMacro(delta.carbs_delta, "У")} ·{" "}
          {signedMacro(delta.protein_delta, "Б")} ·{" "}
          {signedMacro(delta.fat_delta, "Ж")} · {signedKcal(delta.kcal_delta)}
        </div>
      </div>
      {itemCountChanged ? (
        <p className="text-[13px] text-[var(--danger)]">
          Новая модель иначе определила позиции. Проверьте перед сохранением.
        </p>
      ) : null}
      {(comparison.diff.warnings ?? []).map((warning) => (
        <p className="text-[13px] text-[var(--danger)]" key={warning}>
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
      <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
        {label}
      </div>
      <div className="mt-2 text-[12px] text-[var(--fg)]">
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
      <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
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

function SourceTag({ children }: { children: string }) {
  return (
    <span className="border border-[var(--fg)] px-2 py-1 text-[11px]">
      {children}
    </span>
  );
}

function InfoBlock({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <div>
      <h3 className="mb-3 text-[12px] uppercase tracking-[0.02em]">{title}</h3>
      <div className="min-h-16 bg-[rgba(255,255,255,0.42)] p-4">{children}</div>
    </div>
  );
}

function EvidenceRow({ label }: { label: string }) {
  return (
    <div className="grid grid-cols-[24px_1fr] items-center gap-3 py-1">
      <FileText size={16} strokeWidth={1.7} />
      <span className="text-[13px] text-[var(--fg)]">{label}</span>
    </div>
  );
}

function TotalMetric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="font-mono text-[28px] leading-none">
        {numberLabel(value)}
      </div>
      <div className="mt-2 text-[11px] text-[var(--muted)]">{label}</div>
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
            <span className="font-mono text-[18px] text-[var(--fg)]">
              {unit === "ккал" ? formatKcalValue(value) : formatMacroValue(value)}
              <span className="ml-1 text-[11px] text-[var(--muted)]">{unit}</span>
            </span>
            <span className="self-end text-[13px] text-[var(--muted)]">
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
          <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
            {photoFile.isError
              ? "фото недоступно"
              : (photo.original_filename ?? "фото прикреплено")}
          </span>
        </div>
      )}
    </div>
  );
}
