import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, ImagePlus, Plus, X } from "lucide-react";
import {
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  apiErrorMessage,
  apiClient,
  type AutocompleteSuggestion,
  type EstimateCreatedDraftResponse,
  type EstimateMealResponse,
  type MealItemCreate,
  type MealResponse,
  type ReestimateMealResponse,
} from "../../api/client";
import { StatusText } from "../../components/StatusText";
import { FoodImage } from "../../components/FoodImage";
import { Button } from "../../design/primitives/Button";
import {
  formatKcal,
  formatKcalValue,
  formatMacro,
  formatMacroValue,
} from "../../utils/nutritionFormat";
import { toLocalDateTimeString } from "../../utils/dateTime";
import {
  EmptyLog,
  MealRow,
  RightPanel,
  SelectedMealPanel,
  evidenceLabelsForItem,
  numberLabel,
  readableCalculationMethod,
  readableItemSourceKind,
} from "../meals/MealLedger";
import { useBlobObjectUrl } from "../../components/useBlobObjectUrl";
import { useMealsForDate } from "../meals/useMeals";
import {
  localDateKey,
  useNightscoutDayStatus,
  useResyncMealToNightscout,
  useSyncMealToNightscout,
  useSyncTodayToNightscout,
} from "../nightscout/useNightscout";
import { useApiConfig } from "../settings/settingsStore";

type Chip = AutocompleteSuggestion & {
  quantity?: number;
};

type PhotoSource = "file_picker" | "drag_drop" | "clipboard";

type PendingPhoto = {
  id: string;
  file?: File;
  path?: string;
  name: string;
  mimeType?: string;
  sizeBytes?: number;
  previewUrl: string;
  source: PhotoSource;
};

type EstimatePhase =
  | "idle"
  | "reading label"
  | "estimating portion"
  | "building draft";

type ReestimateModel =
  | "default"
  | "gemini-3-flash-preview"
  | "gemini-2.5-flash"
  | "gemini-3.1-flash-lite-preview";
type EstimateModel = ReestimateModel;

type DayTotals = {
  carbs: number;
  kcal: number;
  protein: number;
  fat: number;
  fiber: number;
};

const formatTodayTitle = (date: Date) =>
  new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  })
    .format(date)
    .replace(" г.", "");

const formatWeekday = (date: Date) =>
  new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
  }).format(date);

void formatTodayTitle;
void formatWeekday;

const startOfLocalDay = (date: Date) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate());

const addDays = (date: Date, days: number) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);

const isSameLocalDay = (left: Date, right: Date) =>
  left.getFullYear() === right.getFullYear() &&
  left.getMonth() === right.getMonth() &&
  left.getDate() === right.getDate();

const formatDayTitle = (date: Date) =>
  new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  })
    .format(date)
    .replace(" Рі.", "");

const formatDayWeekday = (date: Date) =>
  new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
  }).format(date);

const buildSelectedDayDateTime = (selectedDate: Date) => {
  const now = new Date();
  return toLocalDateTimeString(
    new Date(
      selectedDate.getFullYear(),
      selectedDate.getMonth(),
      selectedDate.getDate(),
      now.getHours(),
      now.getMinutes(),
      now.getSeconds(),
    ),
  );
};

const sumDayTotals = (meals: MealResponse[]): DayTotals =>
  meals
    .filter((meal) => meal.status === "accepted")
    .reduce(
      (totals, meal) => ({
        carbs: totals.carbs + meal.total_carbs_g,
        kcal: totals.kcal + meal.total_kcal,
        protein: totals.protein + meal.total_protein_g,
        fat: totals.fat + meal.total_fat_g,
        fiber: totals.fiber + meal.total_fiber_g,
      }),
      { carbs: 0, kcal: 0, protein: 0, fat: 0, fiber: 0 },
    );

const namespaceCommandPattern = /^([a-zA-Zа-яА-Я0-9_-]+):(.*)$/;

const findCommandToken = (value: string) => {
  const normalized = value.trim();
  const match = normalized.match(namespaceCommandPattern);
  return match ? `${match[1]}:${match[2] ?? ""}` : "";
};

const removeCommandToken = (value: string, token: string) =>
  value.trim() === token
    ? ""
    : value.replace(new RegExp(escapeRegExp(token)), "").trimStart();

const escapeRegExp = (value: string) =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const suggestionToItem = (
  suggestion: Chip,
  position: number,
): MealItemCreate => {
  const quantity =
    suggestion.kind === "product" ? (suggestion.quantity ?? 1) : 1;
  return {
    name:
      suggestion.kind === "product" && quantity !== 1
        ? `${suggestion.display_name} ×${quantity}`
        : suggestion.display_name,
    carbs_g: suggestion.carbs_g ?? 0,
    protein_g: suggestion.protein_g ?? 0,
    fat_g: suggestion.fat_g ?? 0,
    fiber_g: 0,
    kcal: suggestion.kcal ?? 0,
    source_kind: suggestion.kind === "pattern" ? "pattern" : "product_db",
    calculation_method: "autocomplete_backend_suggestion",
    assumptions: [],
    evidence: {
      token: suggestion.token,
      matched_alias: suggestion.matched_alias,
      quantity,
      source:
        suggestion.kind === "product"
          ? "Взято из сохранённой базы продуктов"
          : undefined,
    },
    warnings: [],
    pattern_id: suggestion.kind === "pattern" ? suggestion.id : null,
    product_id: suggestion.kind === "product" ? suggestion.id : null,
    position,
  };
};

const itemConfidenceTone = (confidence?: number | null) => {
  if (confidence === null || confidence === undefined || confidence < 0.6) {
    return "border-l-[var(--danger)]";
  }
  if (confidence > 0.85) {
    return "border-l-[var(--ok)]";
  }
  return "border-l-[var(--accent)]";
};

const estimatePhaseText: Record<Exclude<EstimatePhase, "idle">, string> = {
  "reading label": "читаю этикетку",
  "estimating portion": "оцениваю порцию",
  "building draft": "собираю черновик",
};

const supportedPhotoTypes = new Set(["image/jpeg", "image/png", "image/webp"]);

const supportedPhotoExtensions = /\.(jpe?g|png|webp)$/i;

const maxPhotoBytes = 10 * 1024 * 1024;

const photoSourceLabels: Record<PhotoSource, string> = {
  file_picker: "файл",
  drag_drop: "перетаскивание",
  clipboard: "буфер",
};

const estimateModelLabels: Record<EstimateModel, string> = {
  default: "По умолчанию backend",
  "gemini-3-flash-preview": "Gemini 3 Flash Preview",
  "gemini-2.5-flash": "Gemini 2.5 Flash",
  "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite",
};

const estimateModelHint: Record<EstimateModel, string> = {
  default: "Будет использован GEMINI_MODEL на backend и fallback-модели при ошибке.",
  "gemini-3-flash-preview": "Принудительно вызвать Gemini 3 Flash Preview.",
  "gemini-2.5-flash": "Принудительно вызвать Gemini 2.5 Flash.",
  "gemini-3.1-flash-lite-preview": "Принудительно вызвать Gemini 3.1 Flash Lite.",
};

const inferMimeType = (name: string) => {
  if (/\.webp$/i.test(name)) {
    return "image/webp";
  }
  if (/\.png$/i.test(name)) {
    return "image/png";
  }
  if (/\.jpe?g$/i.test(name)) {
    return "image/jpeg";
  }
  return "";
};

const photoHasSupportedFormat = (file: File) =>
  supportedPhotoTypes.has(file.type) ||
  supportedPhotoExtensions.test(file.name);

const normalizePhotoFile = (file: File) => {
  if (supportedPhotoTypes.has(file.type)) {
    return file;
  }

  const inferredType = inferMimeType(file.name);
  return inferredType
    ? new File([file], file.name, {
        lastModified: file.lastModified,
        type: inferredType,
      })
    : file;
};

const createPendingPhoto = (file: File, source: PhotoSource): PendingPhoto => {
  const normalizedFile = normalizePhotoFile(file);
  return {
    id: `${normalizedFile.name}-${normalizedFile.size}-${
      globalThis.crypto?.randomUUID?.() ?? Date.now()
    }`,
    file: normalizedFile,
    name: normalizedFile.name,
    mimeType: normalizedFile.type,
    sizeBytes: normalizedFile.size,
    previewUrl: URL.createObjectURL(normalizedFile),
    source,
  };
};

const extractFilesFromDataTransfer = (dataTransfer: DataTransfer) => {
  const filesFromItems = Array.from(dataTransfer.items ?? [])
    .filter((item) => item.kind === "file")
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file));

  return filesFromItems.length
    ? filesFromItems
    : Array.from(dataTransfer.files ?? []);
};

const extractFilesFromClipboard = (clipboardData: DataTransfer) => {
  const filesFromItems = Array.from(clipboardData.items ?? [])
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file));

  return filesFromItems.length
    ? filesFromItems
    : Array.from(clipboardData.files ?? []).filter((file) =>
        file.type.startsWith("image/"),
      );
};

type MealItemResponse = NonNullable<MealResponse["items"]>[number];

const isRememberableLabelItem = (item: MealItemResponse) =>
  item.source_kind === "label_calc" ||
  (item.calculation_method ?? "").startsWith("label_");

const mealItemToCreate = (
  item: MealItemResponse,
  position: number,
): MealItemCreate => ({
  name: item.name,
  brand: item.brand,
  grams: item.grams,
  serving_text: item.serving_text,
  carbs_g: item.carbs_g,
  protein_g: item.protein_g,
  fat_g: item.fat_g,
  fiber_g: item.fiber_g,
  kcal: item.kcal,
  confidence: item.confidence,
  confidence_reason: item.confidence_reason,
  source_kind: item.source_kind,
  calculation_method: item.calculation_method,
  assumptions: item.assumptions ?? [],
  evidence: item.evidence ?? {},
  warnings: item.warnings ?? [],
  pattern_id: item.pattern_id,
  product_id: item.product_id,
  photo_id: item.photo_id,
  position,
});

const mealItemsToCreate = (meal: MealResponse): MealItemCreate[] =>
  (meal.items ?? []).map((item, index) => mealItemToCreate(item, index));

const mealToDraftEstimation = (meal: MealResponse): EstimateMealResponse => ({
  meal_id: meal.id,
  source_photos: (meal.photos ?? []).map((photo, index) => ({
    id: photo.id,
    index: index + 1,
    url: `/photos/${photo.id}/file`,
    thumbnail_url: `/photos/${photo.id}/file`,
    original_filename: photo.original_filename,
  })),
  suggested_items: mealItemsToCreate(meal),
  suggested_totals: {
    total_carbs_g: meal.total_carbs_g,
    total_protein_g: meal.total_protein_g,
    total_fat_g: meal.total_fat_g,
    total_fiber_g: meal.total_fiber_g,
    total_kcal: meal.total_kcal,
  },
  calculation_breakdowns: [],
  gemini_notes: "",
  image_quality_warnings:
    meal.items?.flatMap((item) =>
      (item.warnings ?? []).map((warning) => String(warning)),
    ) ?? [],
  reference_detected: meal.photos?.[0]?.reference_kind ?? "none",
  ai_run_id: meal.id,
  raw_gemini_response: meal.photos?.find((photo) => photo.gemini_response_raw)
    ?.gemini_response_raw,
});

const confirmDiscardDraft = () => {
  try {
    const confirmed = window.confirm(
      "Удалить черновик? Это действие нельзя отменить.",
    );
    return confirmed !== false;
  } catch {
    return true;
  }
};

export function ChatPage() {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  const [selectedDate, setSelectedDate] = useState(() =>
    startOfLocalDay(new Date()),
  );
  const meals = useMealsForDate(selectedDate);
  const [input, setInput] = useState("");
  const [chips, setChips] = useState<Chip[]>([]);
  const commandInputRef = useRef<HTMLInputElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedMealId, setSelectedMealId] = useState<string | null>(null);
  const [selectedSuggestion, setSelectedSuggestion] = useState(0);
  const [debouncedCommand, setDebouncedCommand] = useState("");
  const [autocompleteDismissedToken, setAutocompleteDismissedToken] =
    useState("");
  const [pendingPhotos, setPendingPhotos] = useState<PendingPhoto[]>([]);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [photoPanelOpen, setPhotoPanelOpen] = useState(false);
  const [estimatePhase, setEstimatePhase] = useState<EstimatePhase>("idle");
  const [estimation, setEstimation] = useState<EstimateMealResponse | null>(
    null,
  );
  const [batchEstimation, setBatchEstimation] =
    useState<EstimateMealResponse | null>(null);
  const [draftMealId, setDraftMealId] = useState<string | null>(null);
  const [uploadedPhotosMealId, setUploadedPhotosMealId] = useState<
    string | null
  >(null);
  const [estimateItems, setEstimateItems] = useState<MealItemCreate[]>([]);
  const [estimateEdited, setEstimateEdited] = useState(false);
  const [estimateContextNote, setEstimateContextNote] = useState("");
  const [selectedDraftItems, setSelectedDraftItems] = useState<
    MealItemCreate[]
  >([]);
  const [selectedDraftEdited, setSelectedDraftEdited] = useState(false);
  const [estimateModel, setEstimateModel] = useState<EstimateModel>("default");
  const [reestimateModel, setReestimateModel] =
    useState<ReestimateModel>("gemini-3-flash-preview");
  const [reestimateComparison, setReestimateComparison] =
    useState<ReestimateMealResponse | null>(null);
  const [reestimateError, setReestimateError] = useState<string | null>(null);

  const commandToken = findCommandToken(input);
  const plainAutocompleteQuery = input.trim();
  const autocompleteQuery = commandToken || plainAutocompleteQuery;
  const autocompleteCanQuery = Boolean(
    commandToken || plainAutocompleteQuery.length >= 2,
  );
  const autocompleteOpen = Boolean(
    autocompleteQuery &&
    autocompleteDismissedToken !== autocompleteQuery &&
    autocompleteCanQuery,
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedCommand(autocompleteQuery);
      setSelectedSuggestion(0);
    }, 150);
    return () => window.clearTimeout(timer);
  }, [autocompleteQuery]);

  const autocomplete = useQuery({
    queryKey: ["autocomplete", debouncedCommand],
    queryFn: () => apiClient.autocomplete(config, debouncedCommand),
    enabled: Boolean(config.token.trim() && debouncedCommand && autocompleteOpen),
  });

  const today = startOfLocalDay(new Date());
  const isViewingToday = isSameLocalDay(selectedDate, today);
  const todayMeals = meals.data?.items ?? [];
  const dayTotals = sumDayTotals(todayMeals);
  const selectedDayKey = localDateKey(selectedDate);
  const nightscoutDay = useNightscoutDayStatus(selectedDayKey);
  const syncTodayNightscout = useSyncTodayToNightscout(selectedDayKey);
  const syncMealNightscout = useSyncMealToNightscout(selectedDayKey);
  const resyncMealNightscout = useResyncMealToNightscout(selectedDayKey);
  const selectedMeal =
    todayMeals.find((meal) => meal.id === selectedMealId) ?? null;
  const selectedDraftMeal =
    selectedMeal?.status === "draft" ? selectedMeal : null;
  const selectedDraftEstimation = selectedDraftMeal
    ? mealToDraftEstimation(selectedDraftMeal)
    : null;

  const panelMode = batchEstimation
    ? "batch"
    : estimation
      ? "estimate"
      : autocompleteOpen
        ? "autocomplete"
        : pendingPhotos.length || photoPanelOpen
          ? "photos"
          : selectedDraftMeal
            ? "draft"
            : selectedMeal
              ? "meal"
              : null;

  useEffect(() => {
    if (!selectedDraftMeal) {
      setSelectedDraftItems([]);
      setSelectedDraftEdited(false);
      return;
    }
    setSelectedDraftItems(mealItemsToCreate(selectedDraftMeal));
    setSelectedDraftEdited(false);
  }, [selectedDraftMeal?.id, selectedDraftMeal?.updated_at]);

  useEffect(() => {
    setReestimateComparison(null);
    setReestimateError(null);
  }, [selectedMealId]);

  const invalidateMeals = () =>
    queryClient.invalidateQueries({ queryKey: ["meals"] });

  const createMeal = useMutation({
    mutationFn: apiClient.createMeal.bind(null, config),
    onSuccess: () => {
      invalidateMeals();
      setInput("");
      setChips([]);
    },
  });

  const deleteMeal = useMutation({
    mutationFn: (mealId: string) => apiClient.deleteMeal(config, mealId),
    onSuccess: (_, mealId) => {
      if (selectedMealId === mealId) {
        setSelectedMealId(null);
      }
      invalidateMeals();
    },
  });

  const updateMealTime = useMutation({
    mutationFn: ({ eatenAt, mealId }: { eatenAt: string; mealId: string }) =>
      apiClient.updateMeal(config, mealId, { eaten_at: eatenAt }),
    onSuccess: () => {
      invalidateMeals();
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const updateMealName = useMutation({
    mutationFn: async ({ meal, name }: { meal: MealResponse; name: string }) => {
      const updatedMeal = await apiClient.updateMeal(config, meal.id, {
        title: name,
      });
      const onlyItem = meal.items?.length === 1 ? meal.items[0] : null;
      if (onlyItem) {
        await apiClient.updateMealItem(config, onlyItem.id, { name });
        if (onlyItem.product_id) {
          await apiClient.updateProduct(config, onlyItem.product_id, { name });
        } else if (isRememberableLabelItem(onlyItem)) {
          const product = await apiClient.rememberProductFromMealItem(
            config,
            onlyItem.id,
            [],
          );
          await apiClient.updateProduct(config, product.id, { name });
        }
      }
      return updatedMeal;
    },
    onSuccess: () => {
      invalidateMeals();
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["autocomplete"] });
      queryClient.invalidateQueries({ queryKey: ["database"] });
      queryClient.invalidateQueries({ queryKey: ["database-items"] });
    },
  });

  const saveDraftItems = useMutation({
    mutationFn: ({
      items,
      mealId,
    }: {
      items: MealItemCreate[];
      mealId: string;
    }) => apiClient.replaceMealItems(config, mealId, items),
    onSuccess: () => {
      invalidateMeals();
    },
  });

  const rememberProduct = useMutation({
    mutationFn: ({ aliases, itemId }: { aliases: string[]; itemId: string }) =>
      apiClient.rememberProductFromMealItem(config, itemId, aliases),
    onSuccess: () => {
      invalidateMeals();
      queryClient.invalidateQueries({ queryKey: ["autocomplete"] });
      queryClient.invalidateQueries({ queryKey: ["database"] });
    },
  });

  const reestimateMeal = useMutation({
    mutationFn: async () => {
      if (!selectedMeal) {
        throw new Error("Нет выбранной записи.");
      }
      return apiClient.reestimateMeal(config, selectedMeal.id, {
        model: reestimateModel,
        mode: "compare",
      });
    },
    onSuccess: (comparison) => {
      setReestimateComparison(comparison);
      setReestimateError(null);
    },
    onError: (error) => {
      setReestimateError(
        apiErrorMessage(error, "Не удалось переоценить фото."),
      );
    },
  });

  const applyEstimationRun = useMutation({
    mutationFn: async ({
      applyMode,
      comparison,
    }: {
      applyMode: "replace_current" | "save_as_draft";
      comparison: ReestimateMealResponse;
    }) =>
      apiClient.applyEstimationRun(
        config,
        comparison.meal_id,
        comparison.ai_run_id,
        { apply_mode: applyMode },
      ),
    onSuccess: (result) => {
      setReestimateComparison(null);
      setReestimateError(null);
      setSelectedMealId(result.meal.id);
      invalidateMeals();
    },
  });

  const estimateDraft = useMutation({
    mutationFn: async () => {
      if (!pendingPhotos.length) {
        throw new Error("Добавьте фото для оценки.");
      }
      setPhotoError(null);
      let mealId = draftMealId;
      if (!mealId) {
        setEstimatePhase("reading label");
        const meal = await apiClient.createMeal(config, {
          eaten_at: buildSelectedDayDateTime(selectedDate),
          title: input.trim() || "Еда по фото",
          source: "photo",
          status: "draft",
          items: [],
        });
        mealId = meal.id;
        setDraftMealId(meal.id);
      }

      if (uploadedPhotosMealId !== mealId) {
        setEstimatePhase("estimating portion");
        await uploadPendingPhotos(mealId);
        setUploadedPhotosMealId(mealId);
      }

      setEstimatePhase("building draft");
      return apiClient.estimateAndSaveDraft(config, mealId, {
        use_patterns: [],
        use_products: [],
        model: estimateModel,
        context_note: estimateContextNote.trim() || null,
      });
    },
    onSuccess: (result) => {
      const createdDrafts = result.created_drafts ?? [];
      if (createdDrafts.length > 1) {
        setBatchEstimation(result);
        setEstimation(null);
        setEstimateItems([]);
        setDraftMealId(null);
      } else {
        setBatchEstimation(null);
        setEstimation(result);
        setEstimateItems(result.suggested_items);
        setDraftMealId(createdDrafts[0]?.meal_id ?? result.meal_id);
      }
      setEstimateEdited(false);
      setEstimatePhase("idle");
      clearPendingPhotos();
      setEstimateContextNote("");
      invalidateMeals();
    },
    onError: (error) => {
      setEstimatePhase("idle");
      setPhotoError(
        apiErrorMessage(
          error,
          "Не удалось оценить фото. Проверьте backend и попробуйте еще раз.",
        ),
      );
    },
  });

  const acceptDraft = useMutation({
    mutationFn: async () => {
      if (!draftMealId) {
        throw new Error("Нет активного черновика.");
      }
      return apiClient.acceptMeal(config, draftMealId, estimateItems);
    },
    onSuccess: () => {
      clearEstimate();
      invalidateMeals();
    },
  });

  const discardDraft = useMutation({
    mutationFn: async () => {
      if (!draftMealId) {
        throw new Error("Нет активного черновика.");
      }
      return apiClient.discardMeal(config, draftMealId);
    },
    onSuccess: () => {
      clearEstimate();
      invalidateMeals();
    },
  });

  const acceptSelectedDraft = useMutation({
    mutationFn: async () => {
      if (!selectedDraftMeal) {
        throw new Error("Нет выбранного черновика.");
      }
      return apiClient.acceptMeal(
        config,
        selectedDraftMeal.id,
        selectedDraftItems,
      );
    },
    onSuccess: (meal) => {
      setSelectedMealId(meal.id);
      setSelectedDraftEdited(false);
      invalidateMeals();
    },
  });

  const discardSelectedDraft = useMutation({
    mutationFn: async () => {
      if (!selectedDraftMeal) {
        throw new Error("Нет выбранного черновика.");
      }
      return apiClient.discardMeal(config, selectedDraftMeal.id);
    },
    onSuccess: () => {
      setSelectedMealId(null);
      setSelectedDraftItems([]);
      setSelectedDraftEdited(false);
      invalidateMeals();
    },
  });

  const acceptCreatedDraft = useMutation({
    mutationFn: (draft: EstimateCreatedDraftResponse) =>
      apiClient.acceptMeal(config, draft.meal_id, [draft.item]),
    onSuccess: () => {
      invalidateMeals();
    },
  });

  const discardCreatedDraft = useMutation({
    mutationFn: (draft: EstimateCreatedDraftResponse) =>
      apiClient.discardMeal(config, draft.meal_id),
    onSuccess: () => {
      invalidateMeals();
    },
  });

  const acceptAllCreatedDrafts = useMutation({
    mutationFn: async (drafts: EstimateCreatedDraftResponse[]) => {
      await Promise.all(
        drafts.map((draft) =>
          apiClient.acceptMeal(config, draft.meal_id, [draft.item]),
        ),
      );
    },
    onSuccess: () => {
      setBatchEstimation(null);
      invalidateMeals();
    },
  });

  const discardAllCreatedDrafts = useMutation({
    mutationFn: async (drafts: EstimateCreatedDraftResponse[]) => {
      await Promise.all(
        drafts.map((draft) => apiClient.discardMeal(config, draft.meal_id)),
      );
    },
    onSuccess: () => {
      setBatchEstimation(null);
      invalidateMeals();
    },
  });

  const handleSuggestionSelect = (suggestion: Chip) => {
    setChips((current) => [
      ...current,
      {
        ...suggestion,
        quantity: suggestion.kind === "product" ? 1 : undefined,
      },
    ]);
    setInput((current) =>
      commandToken ? removeCommandToken(current, commandToken) : "",
    );
    setAutocompleteDismissedToken("");
  };

  const handleSubmit = () => {
    const text = input.trim();

    if (chips.length) {
      createMeal.mutate({
        eaten_at: buildSelectedDayDateTime(selectedDate),
        title: chips.map((chip) => chip.display_name).join(", "),
        source: chips.every((chip) => chip.kind === "pattern")
          ? "pattern"
          : "mixed",
        status: "accepted",
        items: chips.map(suggestionToItem),
      });
      return;
    }

    if (text) {
      createMeal.mutate({
        eaten_at: buildSelectedDayDateTime(selectedDate),
        title: text,
        source: "manual",
        status: "accepted",
        items: [
          {
            name: text,
            carbs_g: 0,
            protein_g: 0,
            fat_g: 0,
            fiber_g: 0,
            kcal: 0,
            source_kind: "manual",
            calculation_method: "manual_placeholder",
            assumptions: [],
            evidence: {},
            warnings: [],
            position: 0,
          },
        ],
      });
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (
      (event.metaKey || event.ctrlKey) &&
      event.key === "Enter" &&
      pendingPhotos.length
    ) {
      event.preventDefault();
      estimateDraft.mutate();
      return;
    }

    if (autocompleteOpen && event.key === "Escape") {
      event.preventDefault();
      setAutocompleteDismissedToken(autocompleteQuery);
      return;
    }

    if (autocompleteOpen) {
      const results = autocomplete.data ?? [];
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (results.length) {
          setSelectedSuggestion((index) =>
            Math.min(index + 1, results.length - 1),
          );
        }
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        if (results.length) {
          setSelectedSuggestion((index) => Math.max(index - 1, 0));
        }
        return;
      }
      if (event.key === "Enter" && !event.shiftKey && results.length) {
        event.preventDefault();
        handleSuggestionSelect(results[selectedSuggestion] ?? results[0]);
        return;
      }
    }

    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  const addFilesToPendingPhotos = (
    files: FileList | File[],
    source: PhotoSource,
  ) => {
    const incomingFiles = Array.from(files);
    if (!incomingFiles.length) {
      return;
    }

    const unsupportedFormat = incomingFiles.some(
      (file) => !photoHasSupportedFormat(file),
    );
    const oversizedPhoto = incomingFiles.some(
      (file) => photoHasSupportedFormat(file) && file.size > maxPhotoBytes,
    );
    const supportedFiles = incomingFiles.filter(
      (file) => photoHasSupportedFormat(file) && file.size <= maxPhotoBytes,
    );

    if (unsupportedFormat) {
      setPhotoError("Этот формат фото пока не поддерживается");
    } else if (oversizedPhoto) {
      setPhotoError("Фото больше 10 МБ пока не поддерживаются");
    } else {
      setPhotoError(null);
    }

    if (!supportedFiles.length) {
      setPhotoPanelOpen(true);
      return;
    }

    const next = supportedFiles.map((file) => createPendingPhoto(file, source));
    setPendingPhotos((current) => [...current, ...next]);
    setUploadedPhotosMealId(null);
    setPhotoPanelOpen(true);
  };

  const removePendingPhoto = (id: string) => {
    setPendingPhotos((current) => {
      const photo = current.find((item) => item.id === id);
      if (photo) {
        URL.revokeObjectURL(photo.previewUrl);
      }
      return current.filter((item) => item.id !== id);
    });
    setUploadedPhotosMealId(null);
  };

  const clearPendingPhotos = () => {
    setPendingPhotos((current) => {
      current.forEach((photo) => URL.revokeObjectURL(photo.previewUrl));
      return [];
    });
    setPhotoError(null);
    setUploadedPhotosMealId(null);
  };

  const uploadPendingPhotos = async (mealId: string) => {
    for (const photo of pendingPhotos) {
      if (!photo.file) {
        throw new Error(
          "Этот источник фото не передал файл. Сохраните фото локально и выберите его через «Фото».",
        );
      }
      await apiClient.uploadMealPhoto(config, mealId, photo.file);
    }
  };

  const handlePaste = (event: ClipboardEvent<HTMLElement>) => {
    const pastedFiles = extractFilesFromClipboard(event.clipboardData);
    if (pastedFiles.length) {
      event.preventDefault();
      addFilesToPendingPhotos(pastedFiles, "clipboard");
    }
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const droppedFiles = extractFilesFromDataTransfer(event.dataTransfer);
    if (droppedFiles.length) {
      addFilesToPendingPhotos(droppedFiles, "drag_drop");
    }
  };

  const clearEstimate = () => {
    clearPendingPhotos();
    setPhotoPanelOpen(false);
    setEstimation(null);
    setBatchEstimation(null);
    setDraftMealId(null);
    setUploadedPhotosMealId(null);
    setEstimateItems([]);
    setEstimateEdited(false);
    setInput("");
  };

  const persistActiveDraftEdits = () => {
    if (estimation && draftMealId && estimateEdited) {
      saveDraftItems.mutate({ mealId: draftMealId, items: estimateItems });
    }
    if (selectedDraftMeal && selectedDraftEdited) {
      saveDraftItems.mutate({
        mealId: selectedDraftMeal.id,
        items: selectedDraftItems,
      });
    }
  };

  const handleMealToggle = (meal: MealResponse) => {
    persistActiveDraftEdits();
    setSelectedMealId((current) => (current === meal.id ? null : meal.id));
    if (estimation) {
      setEstimation(null);
      setDraftMealId(null);
      setEstimateItems([]);
      setEstimateEdited(false);
    }
    if (batchEstimation) {
      setBatchEstimation(null);
    }
    setPhotoPanelOpen(false);
  };

  const clearActivePanelState = () => {
    setSelectedMealId(null);
    setSelectedDraftItems([]);
    setSelectedDraftEdited(false);
    setPhotoPanelOpen(false);
    setReestimateComparison(null);
    setReestimateError(null);
    if (estimation) {
      setEstimation(null);
      setDraftMealId(null);
      setEstimateItems([]);
      setEstimateEdited(false);
    }
    if (batchEstimation) {
      setBatchEstimation(null);
    }
  };

  const navigateToDate = (nextDate: Date) => {
    persistActiveDraftEdits();
    clearActivePanelState();
    setSelectedDate(startOfLocalDay(nextDate));
  };

  const handleGoToPreviousDay = () => navigateToDate(addDays(selectedDate, -1));

  const handleGoToToday = () => navigateToDate(today);

  const handleGoToNextDay = () => {
    if (isViewingToday) {
      return;
    }
    const nextDate = addDays(selectedDate, 1);
    navigateToDate(nextDate > today ? today : nextDate);
  };

  const emptyDayMessage = isViewingToday
    ? "Сегодня пока нет записей."
    : `За ${formatDayTitle(selectedDate)} пока нет записей.`;

  return (
    <div
      className="h-screen overflow-hidden bg-[var(--bg)]"
      onDragOver={(event) => event.preventDefault()}
      onDrop={handleDrop}
      onPaste={handlePaste}
    >
      <div
        className={`flex h-screen min-h-0 flex-col px-10 py-9 transition-[padding] duration-200 ease-out ${
          panelMode ? "pr-[452px]" : ""
        }`}
      >
        <header className="shrink-0 grid gap-7">
          <div className="grid grid-cols-[1fr_auto] items-start gap-8">
            <div>
              <p className="text-[16px] text-[var(--fg)]">
                {formatDayWeekday(selectedDate)}
              </p>
              <h1 className="mt-5 whitespace-nowrap font-mono text-[56px] font-normal leading-none text-[var(--fg)]">
                {formatDayTitle(selectedDate)}
              </h1>
            </div>
            <div className="hidden items-center gap-3 pt-12 xl:flex">
              <button
                className="h-10 w-10 border border-[var(--hairline)] bg-[var(--surface)] text-[18px]"
                onClick={handleGoToPreviousDay}
                aria-label="Предыдущий день"
                type="button"
              >
                {"<"}
              </button>
              <button
                className="h-10 border border-[var(--hairline)] bg-[var(--surface)] px-5 text-[13px] font-medium"
                onClick={handleGoToToday}
                aria-label="Вернуться к сегодня"
                type="button"
              >
                Сегодня
              </button>
              <button
                aria-label="Следующий день"
                className="h-10 w-10 border border-[var(--hairline)] bg-[var(--surface)] text-[18px] disabled:opacity-40"
                disabled={isViewingToday}
                onClick={handleGoToNextDay}
                type="button"
              >
                {">"}
              </button>
            </div>
          </div>
          <DailySummary totals={dayTotals} />
          <div className="flex flex-wrap items-center justify-between gap-3 border-y border-[var(--hairline)] py-3 text-[12px] text-[var(--muted)]">
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={`h-2 w-2 rounded-full ${
                  nightscoutDay.data?.connected
                    ? "bg-[var(--ok)]"
                    : "bg-[var(--hairline)]"
                }`}
              />
              <span>
                {nightscoutDay.data?.connected
                  ? "Nightscout подключён"
                  : "Nightscout не подключён"}
              </span>
              {nightscoutDay.data?.configured ? (
                <>
                  <span>несинхронизировано: {nightscoutDay.data.unsynced_meals_count}</span>
                  {nightscoutDay.data.last_sync_at ? (
                    <span>
                      последняя синхронизация:{" "}
                      {new Intl.DateTimeFormat("ru-RU", {
                        hour: "2-digit",
                        minute: "2-digit",
                      }).format(new Date(nightscoutDay.data.last_sync_at))}
                    </span>
                  ) : null}
                </>
              ) : (
                <a className="underline" href="/settings">
                  Настроить
                </a>
              )}
            </div>
            <button
              className="border border-[var(--hairline)] bg-[var(--surface)] px-3 py-2 text-[12px] uppercase tracking-[0.06em] disabled:opacity-40"
              disabled={
                !nightscoutDay.data?.configured ||
                !nightscoutDay.data?.connected ||
                !nightscoutDay.data?.unsynced_meals_count ||
                syncTodayNightscout.isPending
              }
              onClick={() => syncTodayNightscout.mutate()}
              type="button"
            >
              {syncTodayNightscout.isPending
                ? "Отправляю..."
                : "Отправить день в Nightscout"}
            </button>
            {syncTodayNightscout.data ? (
              <span className="w-full text-[12px] text-[var(--fg)]">
                Отправлено: {syncTodayNightscout.data.sent_count}, пропущено:{" "}
                {syncTodayNightscout.data.skipped_count}, ошибок:{" "}
                {syncTodayNightscout.data.failed_count}
              </span>
            ) : null}
          </div>
        </header>

        <section className="mt-7 min-h-0 flex-1 overflow-y-auto pr-2">
          <div className="grid gap-0">
            {!config.token.trim() ? (
              <EmptyLog message="Укажите адрес backend и токен в настройках." />
            ) : null}
            {config.token.trim() && meals.isLoading ? (
              <EmptyLog message="Загружаю еду." />
            ) : null}
            {config.token.trim() && meals.isSuccess && !todayMeals.length ? (
              <EmptyLog message={emptyDayMessage} />
            ) : null}
            {todayMeals.map((meal) => (
              <MealRow
                key={meal.id}
                meal={meal}
                selected={selectedMealId === meal.id}
                onToggle={() => handleMealToggle(meal)}
              />
            ))}
          </div>
        </section>

        <section className="shrink-0 pt-4">
          <div className="mb-3 flex flex-wrap gap-2">
            {chips.map((chip, index) => (
              <div
                className="flex items-center gap-2 border border-[var(--hairline)] bg-[var(--surface)] px-2 py-1 text-[12px] uppercase tracking-[0.06em]"
                key={`${chip.token}-${index}`}
              >
                <button
                  aria-label={chip.token}
                  onClick={() =>
                    setChips((current) =>
                      current.filter((_, chipIndex) => chipIndex !== index),
                    )
                  }
                  type="button"
                >
                  {chip.token} <span className="text-[var(--muted)]">x</span>
                </button>
                {chip.kind === "product" ? (
                  <label className="flex items-center gap-1 normal-case tracking-normal text-[var(--muted)]">
                    <span>Количество</span>
                    <input
                      aria-label={`Количество ${chip.display_name}`}
                      className="h-6 w-14 border border-[var(--hairline)] bg-[var(--bg)] px-1 text-right font-mono text-[12px] text-[var(--fg)] outline-none"
                      min="0.1"
                      onChange={(event) => {
                        const rawValue = event.target.value;
                        const value = Number(event.target.value);
                        setChips((current) =>
                          current.map((currentChip, chipIndex) =>
                            chipIndex === index
                              ? {
                                  ...currentChip,
                                  quantity:
                                    rawValue === ""
                                      ? undefined
                                      : Number.isFinite(value) && value > 0
                                        ? value
                                        : 1,
                                }
                              : currentChip,
                          ),
                        );
                      }}
                      step="0.5"
                      type="number"
                      value={chip.quantity ?? ""}
                    />
                    <span>шт</span>
                  </label>
                ) : null}
              </div>
            ))}
          </div>

          {estimatePhase !== "idle" ? (
            <div className="mb-3 text-[12px] uppercase tracking-[0.06em] text-[var(--accent)] transition duration-200 ease-out">
              Оцениваю фото... {estimatePhaseText[estimatePhase]}
            </div>
          ) : null}

          <form
            className="relative grid grid-cols-[48px_minmax(0,1fr)_auto] items-center gap-3 border-t border-[var(--hairline)] pt-6"
            onSubmit={(event) => {
              event.preventDefault();
              handleSubmit();
            }}
          >
            <button
              aria-label="Добавить еду"
              className="flex h-12 w-12 items-center justify-center border border-[var(--hairline)] bg-[var(--surface)] text-[var(--fg)]"
              onClick={() => commandInputRef.current?.focus()}
              type="button"
            >
              <Plus size={22} strokeWidth={1.7} />
            </button>
            <label className="sr-only" htmlFor="command-input">
              Командный ввод
            </label>
            <div className="relative">
              <input
                className="h-14 w-full border border-[var(--hairline)] bg-[var(--surface)] px-11 pr-14 font-mono text-[24px] leading-none outline-none transition placeholder:text-[var(--muted)] focus:border-[var(--fg)]"
                id="command-input"
                onChange={(event) => {
                  setInput(event.target.value);
                  setAutocompleteDismissedToken("");
                }}
                onKeyDown={handleKeyDown}
                placeholder="bk:whopper"
                ref={commandInputRef}
                value={input}
              />
              <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[18px] text-[var(--muted)]">
                {">"}
              </span>
              {input ? (
                <button
                  aria-label="Очистить команду"
                  className="absolute right-14 top-1/2 -translate-y-1/2 text-[var(--muted)]"
                  onClick={() => {
                    setInput("");
                    setAutocompleteDismissedToken("");
                  }}
                  type="button"
                >
                  <X size={17} />
                </button>
              ) : null}
              <button
                aria-label="Записать"
                className="absolute right-1 top-1/2 flex h-12 w-12 -translate-y-1/2 items-center justify-center bg-[var(--fg)] text-[var(--surface)]"
                disabled={createMeal.isPending}
                onClick={handleSubmit}
                type="button"
              >
                <ArrowRight size={20} />
              </button>
            </div>
            <button
              aria-label="Фото"
              className="flex h-12 items-center gap-2 border border-[var(--hairline)] bg-[var(--surface)] px-4 text-[13px] text-[var(--fg)]"
              onClick={() => {
                setPhotoPanelOpen(true);
                imageInputRef.current?.click();
              }}
              type="button"
            >
              <ImagePlus size={20} strokeWidth={1.7} />
              <span>Фото</span>
            </button>
            <input
              accept="image/jpeg,image/png,image/webp"
              aria-label="Выбрать фото"
              className="sr-only"
              multiple
              onChange={(event) => {
                if (event.target.files?.length) {
                  addFilesToPendingPhotos(event.target.files, "file_picker");
                  event.target.value = "";
                }
              }}
              ref={imageInputRef}
              type="file"
            />
          </form>
        </section>
      </div>

      <RightPanel open={Boolean(panelMode)}>
        {panelMode === "batch" && batchEstimation ? (
          <BatchEstimatePanel
            drafts={batchEstimation.created_drafts ?? []}
            onAcceptAll={(drafts) => acceptAllCreatedDrafts.mutate(drafts)}
            onDiscardAll={(drafts) => {
              if (confirmDiscardDraft()) {
                discardAllCreatedDrafts.mutate(drafts);
              }
            }}
            onDiscardOne={(draft) => {
              if (confirmDiscardDraft()) {
                discardCreatedDraft.mutate(draft);
              }
            }}
            onOpen={(draft) => {
              setSelectedMealId(draft.meal_id);
              setBatchEstimation(null);
            }}
            onSaveOne={(draft) => acceptCreatedDraft.mutate(draft)}
            saving={
              acceptCreatedDraft.isPending ||
              discardCreatedDraft.isPending ||
              acceptAllCreatedDrafts.isPending ||
              discardAllCreatedDrafts.isPending
            }
            warnings={batchEstimation.image_quality_warnings}
          />
        ) : null}
        {panelMode === "autocomplete" ? (
          <AutocompletePanel
            activeIndex={selectedSuggestion}
            loading={autocomplete.isFetching}
            onSelect={handleSuggestionSelect}
            results={autocomplete.data ?? []}
            token={autocompleteQuery}
          />
        ) : null}
        {panelMode === "meal" && selectedMeal ? (
          <SelectedMealPanel
            applyingReestimate={applyEstimationRun.isPending}
            deletePending={deleteMeal.isPending}
            meal={selectedMeal}
            onDelete={(meal) => deleteMeal.mutate(meal.id)}
            onReestimate={() => reestimateMeal.mutate()}
            onReestimateApply={(mode, comparison) =>
              applyEstimationRun.mutate({ applyMode: mode, comparison })
            }
            onReestimateCancel={() => setReestimateComparison(null)}
            onRememberProduct={(item, aliases) =>
              rememberProduct.mutate({ aliases, itemId: item.id })
            }
            onSyncNightscout={(meal) => syncMealNightscout.mutate(meal.id)}
            onResyncNightscout={(meal) => resyncMealNightscout.mutate(meal.id)}
            onUpdateName={(meal, name) =>
              updateMealName.mutate({ meal, name })
            }
            onUpdateTime={(meal, eatenAt) =>
              updateMealTime.mutate({ eatenAt, mealId: meal.id })
            }
            rememberPending={rememberProduct.isPending}
            reestimateComparison={reestimateComparison}
            reestimateError={reestimateError}
            reestimateModel={reestimateModel}
            reestimatePending={reestimateMeal.isPending}
            onReestimateModelChange={setReestimateModel}
            syncNightscoutPending={
              syncMealNightscout.isPending || resyncMealNightscout.isPending
            }
            updateNamePending={updateMealName.isPending}
            updateTimePending={updateMealTime.isPending}
          />
        ) : null}
        {panelMode === "draft" && selectedDraftEstimation ? (
          <EstimatePanel
            edited={selectedDraftEdited}
            estimation={selectedDraftEstimation}
            items={selectedDraftItems}
            onChangeItem={(index, next) => {
              setSelectedDraftItems((current) =>
                current.map((item, itemIndex) =>
                  itemIndex === index ? { ...item, ...next } : item,
                ),
              );
              setSelectedDraftEdited(true);
            }}
            onDiscard={() => {
              if (confirmDiscardDraft()) {
                discardSelectedDraft.mutate();
              }
            }}
            onSave={() => acceptSelectedDraft.mutate()}
            saving={
              acceptSelectedDraft.isPending ||
              discardSelectedDraft.isPending ||
              saveDraftItems.isPending
            }
          />
        ) : null}
        {panelMode === "photos" ? (
          <PendingPhotoPanel
            contextNote={estimateContextNote}
            estimateModel={estimateModel}
            estimating={estimateDraft.isPending}
            error={photoError}
            onChangeContextNote={setEstimateContextNote}
            onChangeModel={setEstimateModel}
            onClear={clearPendingPhotos}
            onEstimate={() => estimateDraft.mutate()}
            onRemove={removePendingPhoto}
            photos={pendingPhotos}
          />
        ) : null}
        {panelMode === "estimate" && estimation ? (
          <EstimatePanel
            edited={estimateEdited}
            estimation={estimation}
            items={estimateItems}
            onChangeItem={(index, next) => {
              setEstimateItems((current) =>
                current.map((item, itemIndex) =>
                  itemIndex === index ? { ...item, ...next } : item,
                ),
              );
              setEstimateEdited(true);
            }}
            onDiscard={() => {
              if (confirmDiscardDraft()) {
                discardDraft.mutate();
              }
            }}
            onSave={() => acceptDraft.mutate()}
            saving={acceptDraft.isPending || discardDraft.isPending}
          />
        ) : null}
      </RightPanel>
    </div>
  );
}

function DailySummary({ totals }: { totals: DayTotals }) {
  const progress = Math.min(100, Math.max(0, (totals.kcal / 2200) * 100));
  const metrics = [
    ["углеводы", totals.carbs, "г"],
    ["ккал", totals.kcal, "ккал"],
    ["белки", totals.protein, "г"],
    ["жиры", totals.fat, "г"],
    ["клетчатка", totals.fiber, "г"],
  ] as const;

  return (
    <section className="grid gap-6">
      <div className="grid grid-cols-[repeat(5,minmax(74px,1fr))] gap-6">
        {metrics.map(([label, value, unit]) => (
          <div className="grid gap-2" key={label}>
            <span className="text-[11px] uppercase tracking-[0.02em] text-[var(--fg)]">
              {label}
            </span>
            <span className="font-mono text-[34px] leading-none text-[var(--fg)]">
              {numberLabel(value)}
              <span className="ml-2 text-[12px] lowercase tracking-normal text-[var(--fg)]">
                {unit}
              </span>
            </span>
          </div>
        ))}
      </div>
      <div className="grid gap-3">
        <div
          aria-label="Прогресс цели на день"
          className="h-[3px] bg-[var(--hairline)]"
          role="progressbar"
          aria-valuemax={100}
          aria-valuemin={0}
          aria-valuenow={Math.round(progress)}
        >
          <div
            className="h-[3px] bg-[var(--fg)]"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="grid grid-cols-2 text-[12px] text-[var(--fg)]">
          <span>Цель на день: 2200 ккал</span>
          <span className="text-right">
            {numberLabel(totals.kcal)} / 2200 ккал
          </span>
        </div>
      </div>
    </section>
  );
}

function PendingPhotoPanel({
  contextNote,
  error,
  estimateModel,
  estimating,
  onChangeContextNote,
  onChangeModel,
  onClear,
  onEstimate,
  onRemove,
  photos,
}: {
  contextNote: string;
  error: string | null;
  estimateModel: EstimateModel;
  estimating: boolean;
  onChangeContextNote: (value: string) => void;
  onChangeModel: (model: EstimateModel) => void;
  onClear: () => void;
  onEstimate: () => void;
  onRemove: (id: string) => void;
  photos: PendingPhoto[];
}) {
  return (
    <div className="flex h-full min-w-0 flex-col overflow-x-hidden px-7 py-8">
      <div className="border-b border-[var(--hairline)] pb-6">
        <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          фото к оценке
        </p>
        <h2 className="mt-4 font-mono text-[34px] font-normal leading-none text-[var(--fg)]">
          {photos.length ? `${photos.length} фото` : "добавьте фото"}
        </h2>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {!photos.length ? (
          <div className="border-b border-[var(--hairline)] py-6">
            <p className="text-[15px] leading-snug text-[var(--fg)]">
              Перетащите фото из Связи с телефоном или Проводника Windows
            </p>
            <p className="mt-3 text-[13px] leading-snug text-[var(--muted)]">
              Фото не отправляются в облако, они загружаются только в ваш
              локальный backend
            </p>
          </div>
        ) : null}

        {photos.map((photo) => (
          <div
            className="grid grid-cols-[56px_1fr_auto] items-center gap-4 border-b border-[var(--hairline)] py-4"
            key={photo.id}
          >
            <img
              alt={photo.name}
              className="h-14 w-14 border border-[var(--hairline)] object-cover"
              src={photo.previewUrl}
            />
            <div className="min-w-0">
              <div className="truncate text-[15px] text-[var(--fg)]">
                {photo.name}
              </div>
              <div className="mt-1 text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                {photoSourceLabels[photo.source]}
                {photo.mimeType ? ` / ${photo.mimeType}` : ""}
              </div>
            </div>
            <button
              className="text-[12px] uppercase tracking-[0.06em] text-[var(--danger)]"
              onClick={() => onRemove(photo.id)}
              type="button"
            >
              Удалить
            </button>
          </div>
        ))}
      </div>

      {estimating ? (
        <div className="border-t border-[var(--hairline)] py-4 text-[12px] uppercase tracking-[0.06em] text-[var(--accent)]">
          Оцениваю фото...
        </div>
      ) : null}
      {error ? (
        <p className="border-t border-[var(--hairline)] py-4 text-[13px] text-[var(--danger)]">
          {error}
        </p>
      ) : null}

      <div className="sticky bottom-0 mt-auto grid gap-3 border-t border-[var(--hairline)] bg-[var(--bg)] py-4">
        <label className="grid gap-2 border-b border-[var(--hairline)] pb-4 text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
          Контекст для фото
          <textarea
            aria-label="Контекст для фото"
            className="min-h-20 resize-none border border-[var(--hairline)] bg-[var(--surface)] px-3 py-2 text-[13px] normal-case leading-snug tracking-normal text-[var(--fg)] outline-none"
            disabled={estimating}
            maxLength={1200}
            onChange={(event) => onChangeContextNote(event.target.value)}
            placeholder="например: 100 г варёного риса, половина тортильи, без соуса"
            value={contextNote}
          />
          <span className="text-[11px] normal-case tracking-normal text-[var(--muted)]">
            Этот текст отправляется только в backend как подсказка для оценки.
          </span>
        </label>
        <div className="grid gap-2 border-b border-[var(--hairline)] pb-4">
          <label className="grid gap-2 text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
            Модель оценки
            <select
              aria-label="Модель оценки фото"
              className="border border-[var(--hairline)] bg-[var(--surface)] px-3 py-2 text-[13px] normal-case tracking-normal text-[var(--fg)] outline-none"
              disabled={estimating}
              onChange={(event) =>
                onChangeModel(event.target.value as EstimateModel)
              }
              value={estimateModel}
            >
              <option value="default">По умолчанию backend</option>
              <option value="gemini-3-flash-preview">
                Gemini 3 Flash Preview
              </option>
              <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
              <option value="gemini-3.1-flash-lite-preview">
                Gemini 3.1 Flash Lite
              </option>
            </select>
          </label>
          <p className="text-[12px] leading-snug text-[var(--muted)]">
            Сейчас: {estimateModelLabels[estimateModel]}.{" "}
            {estimateModelHint[estimateModel]}
          </p>
        </div>
        <Button
          disabled={!photos.length || estimating}
          icon={<ImagePlus size={16} />}
          onClick={onEstimate}
          variant="primary"
        >
          {error ? "Повторить оценку" : "Оценить"}
        </Button>
        <Button disabled={!photos.length || estimating} onClick={onClear}>
          Очистить фото
        </Button>
      </div>
    </div>
  );
}

function AutocompletePanel({
  activeIndex,
  loading,
  onSelect,
  results,
  token,
}: {
  activeIndex: number;
  loading: boolean;
  onSelect: (suggestion: Chip) => void;
  results: Chip[];
  token: string;
}) {
  return (
    <div className="flex h-full flex-col px-7 py-8">
      <div className="border-b border-[var(--hairline)] pb-6">
        <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          автозаполнение
        </p>
        <h2 className="mt-4 break-all font-mono text-[42px] font-normal leading-none text-[var(--fg)]">
          {token}
        </h2>
      </div>

      <div className="mt-6 border-b border-[var(--hairline)] pb-3">
        <p className="text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
          частые
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        {loading ? (
          <div className="border-b border-[var(--hairline)] px-5 py-3">
            <StatusText>Поиск</StatusText>
          </div>
        ) : null}
        {results.length ? (
          results.map((result, index) => (
            <button
              className={`grid w-full min-w-0 grid-cols-[48px_minmax(0,1fr)] items-center gap-4 border-b border-[var(--hairline)] py-4 text-left ${
                activeIndex === index ? "bg-[var(--bg)]" : ""
              }`}
              key={`${result.kind}-${result.id ?? result.token}`}
              onClick={() => onSelect(result)}
              type="button"
            >
              <FoodImage
                alt={`${result.display_name} фото`}
                className="h-10 w-10"
                fit="contain"
                src={result.image_url}
              />
              <span className="grid min-w-0 gap-1">
                <span className="truncate text-[15px] text-[var(--fg)]">
                  {result.display_name}
                </span>
                <span className="truncate text-[12px] text-[var(--muted)]">
                  {suggestionKindLabel(result)} · {result.subtitle ?? result.token}
                </span>
                <span className="mt-3 flex min-w-0 flex-wrap justify-end gap-x-3 gap-y-1 text-right">
                  <AutocompleteMacro value={result.carbs_g} unit="У" />
                  <AutocompleteMacro value={result.protein_g} unit="Б" />
                  <AutocompleteMacro value={result.fat_g} unit="Ж" />
                  <span className="whitespace-nowrap font-mono text-[13px]">
                    {formatKcal(result.kcal)}
                  </span>
                </span>
              </span>
            </button>
          ))
        ) : !loading ? (
          <p className="border-b border-[var(--hairline)] py-4 text-[13px] text-[var(--muted)]">
            Ничего не найдено
          </p>
        ) : null}
      </div>
      <button
        className="sticky bottom-0 grid w-full grid-cols-[1fr_auto] border-t border-[var(--hairline)] bg-[var(--bg)] py-4 text-left text-[13px] text-[var(--fg)]"
        type="button"
      >
        <span>Показать все результаты для «{token}»</span>
        <span className="font-mono text-[18px]">-&gt;</span>
      </button>
    </div>
  );
}

function AutocompleteMacro({
  unit,
  value,
}: {
  unit: string;
  value: number | null | undefined;
}) {
  return (
    <span className="whitespace-nowrap text-right font-mono text-[13px]">
      {formatMacro(value, unit)}
    </span>
  );
}

function suggestionKindLabel(result: Chip) {
  if (result.kind === "product") {
    return "Сохранённое";
  }
  if (/^(bk|mc|rostics|vit):/i.test(result.token)) {
    return "Ресторан";
  }
  return "Шаблон";
}

function BatchEstimatePanel({
  drafts,
  onAcceptAll,
  onDiscardAll,
  onDiscardOne,
  onOpen,
  onSaveOne,
  saving,
  warnings,
}: {
  drafts: EstimateCreatedDraftResponse[];
  onAcceptAll: (drafts: EstimateCreatedDraftResponse[]) => void;
  onDiscardAll: (drafts: EstimateCreatedDraftResponse[]) => void;
  onDiscardOne: (draft: EstimateCreatedDraftResponse) => void;
  onOpen: (draft: EstimateCreatedDraftResponse) => void;
  onSaveOne: (draft: EstimateCreatedDraftResponse) => void;
  saving: boolean;
  warnings: string[];
}) {
  return (
    <div className="flex h-full flex-col overflow-y-auto px-7 py-8">
      <section className="border-b border-[var(--hairline)] pb-6">
        <p className="text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
          Результат оценки
        </p>
        <h2 className="mt-3 text-[30px] leading-none text-[var(--fg)]">
          Создано черновиков: {drafts.length}
        </h2>
        {warnings.length ? (
          <div className="mt-5 grid gap-2">
            {warnings.map((warning) => (
              <EvidenceLine key={warning} label={warning} />
            ))}
          </div>
        ) : null}
      </section>

      <section className="grid gap-0 border-b border-[var(--hairline)]">
        {drafts.map((draft, index) => (
          <article
            className="grid gap-4 border-b border-[var(--hairline)] py-5 last:border-b-0"
            key={draft.meal_id}
          >
            <div className="grid grid-cols-[72px_1fr] gap-4">
              {draft.source_photo_id ? (
                <SourcePhotoImage
                  alt={`${draft.title} фото`}
                  photoId={draft.source_photo_id}
                  size="item"
                />
              ) : (
                <div className="flex h-[72px] w-[72px] items-center justify-center border border-[var(--hairline)] bg-[var(--surface)] text-[var(--muted)]">
                  <ImagePlus size={20} strokeWidth={1.5} />
                </div>
              )}
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
                  {index + 1}. Фото / черновик
                </div>
                <h3 className="mt-2 truncate text-[20px] leading-tight text-[var(--fg)]">
                  {draft.title}
                </h3>
                <div className="mt-3 grid grid-cols-4 gap-2 font-mono text-[14px]">
                  <span>{formatMacroValue(draft.totals.total_carbs_g)}У</span>
                  <span>{formatMacroValue(draft.totals.total_protein_g)}Б</span>
                  <span>{formatMacroValue(draft.totals.total_fat_g)}Ж</span>
                  <span className="text-right">
                    {formatKcalValue(draft.totals.total_kcal)} ккал
                  </span>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Button disabled={saving} onClick={() => onOpen(draft)}>
                Открыть
              </Button>
              <Button
                disabled={saving}
                onClick={() => onSaveOne(draft)}
                variant="primary"
              >
                Сохранить
              </Button>
              <Button
                disabled={saving}
                onClick={() => onDiscardOne(draft)}
                variant="danger"
              >
                Удалить
              </Button>
            </div>
          </article>
        ))}
      </section>

      <div className="sticky bottom-0 mt-auto grid gap-3 border-t border-[var(--hairline)] bg-[var(--bg)] py-4">
        <Button
          disabled={saving || !drafts.length}
          onClick={() => onAcceptAll(drafts)}
          variant="primary"
        >
          Сохранить все
        </Button>
        <Button
          disabled={saving || !drafts.length}
          onClick={() => onDiscardAll(drafts)}
          variant="danger"
        >
          Удалить все черновики
        </Button>
      </div>
    </div>
  );
}

type EstimateSourcePhoto = NonNullable<
  EstimateMealResponse["source_photos"]
>[number];

const estimateEvidenceRecord = (item: MealItemCreate) =>
  item.evidence &&
  typeof item.evidence === "object" &&
  !Array.isArray(item.evidence)
    ? (item.evidence as Record<string, unknown>)
    : {};

const estimateSourcePhotoIds = (item: MealItemCreate) => {
  const sourcePhotoIds = estimateEvidenceRecord(item).source_photo_ids;
  const ids = Array.isArray(sourcePhotoIds)
    ? sourcePhotoIds.map((value) => String(value))
    : [];
  if (item.photo_id && !ids.includes(item.photo_id)) {
    ids.push(item.photo_id);
  }
  return ids;
};

const estimateSourcePhotoIndices = (item: MealItemCreate) => {
  const sourcePhotoIndices = estimateEvidenceRecord(item).source_photo_indices;
  return Array.isArray(sourcePhotoIndices)
    ? sourcePhotoIndices
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value))
    : [];
};

const estimatePrimaryPhotoId = (item: MealItemCreate) => {
  const evidence = estimateEvidenceRecord(item);
  const primaryPhotoId = evidence.primary_photo_id;
  if (primaryPhotoId) {
    return String(primaryPhotoId);
  }
  return item.photo_id ?? estimateSourcePhotoIds(item)[0] ?? null;
};

const estimateItemTypeLabel = (item: MealItemCreate) => {
  const itemType = estimateEvidenceRecord(item).item_type;
  if (itemType === "drink") {
    return "напиток";
  }
  if (itemType === "packaged_food") {
    return "упаковка";
  }
  if (itemType === "plated_food") {
    return "фото-еда";
  }
  if (itemType === "restaurant_item") {
    return "ресторан";
  }
  return readableItemSourceKind(item.source_kind);
};

const estimatePhotoUsageText = (
  item: MealItemCreate,
  photos: EstimateSourcePhoto[],
) => {
  const byId = new Map(photos.map((photo) => [photo.id, photo.index]));
  const indices = [
    ...estimateSourcePhotoIds(item)
      .map((id) => byId.get(id))
      .filter((value): value is number => value !== undefined),
    ...estimateSourcePhotoIndices(item),
  ];
  const unique = Array.from(new Set(indices)).sort((a, b) => a - b);
  return unique.length ? unique.join(", ") : "не связано";
};

const estimateItemEvidenceRows = (item: MealItemCreate) =>
  evidenceLabelsForItem(item).filter(Boolean);

const estimateItemAssumptions = (item: MealItemCreate) =>
  (item.assumptions ?? [])
    .map((assumption) => String(assumption))
    .filter(Boolean);

function EstimatePanel({
  edited,
  estimation,
  items,
  onChangeItem,
  onDiscard,
  onSave,
  saving,
}: {
  edited: boolean;
  estimation: EstimateMealResponse;
  items: MealItemCreate[];
  onChangeItem: (index: number, item: Partial<MealItemCreate>) => void;
  onDiscard: () => void;
  onSave: () => void;
  saving: boolean;
}) {
  const primaryItem = items[0];
  const breakdowns = estimation.calculation_breakdowns ?? [];
  const primaryBreakdown = breakdowns[0];
  const sourcePhotos = estimation.source_photos ?? [];
  const confidence = primaryItem?.confidence;
  const confidenceLabel =
    confidence === null || confidence === undefined
      ? "--"
      : confidence.toFixed(2);
  const assumptions = (
    primaryBreakdown?.assumptions ??
    items.flatMap((item) =>
      (item.assumptions ?? []).map((assumption) => String(assumption)),
    )
  ).filter(Boolean);
  const evidenceRows = (
    primaryBreakdown?.evidence?.length
      ? primaryBreakdown.evidence
      : items.flatMap((item) => evidenceLabelsForItem(item))
  ).filter(Boolean);
  const subtitle =
    primaryItem?.serving_text ??
    (primaryBreakdown?.count_detected && primaryBreakdown.net_weight_per_unit_g
      ? `×${primaryBreakdown.count_detected} упаковки · ${formatMacroValue(
          primaryBreakdown.net_weight_per_unit_g,
        )} г каждая`
      : null);

  return (
    <div className="flex h-full flex-col overflow-y-auto px-7 py-8">
      <section className="border-b border-[var(--hairline)] pb-6">
        <SourcePhotoPreview photos={sourcePhotos} />
        {sourcePhotos.length > 1 ? (
          <div className="mt-3 grid grid-cols-5 gap-2">
            {sourcePhotos.slice(0, 5).map((photo) => (
              <SourcePhotoThumb key={photo.id} photoId={photo.id} />
            ))}
          </div>
        ) : null}
      </section>

      <SourcePhotosDebug photos={sourcePhotos} />

      {estimation.image_quality_warnings.length ? (
        <section className="border-b border-[var(--hairline)] py-5">
          <h3 className="text-[13px] uppercase tracking-[0.02em]">проверьте</h3>
          <div className="mt-3 grid gap-2">
            {estimation.image_quality_warnings.map((warning) => (
              <EvidenceLine key={warning} label={warning} />
            ))}
          </div>
        </section>
      ) : null}

      <div className="grid grid-cols-[1fr_auto] gap-4 border-b border-[var(--hairline)] py-6">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
            черновик
          </p>
          <h2 className="mt-3 text-[26px] leading-tight text-[var(--fg)]">
            {primaryItem?.name ?? "Еда по фото"}
          </h2>
          {subtitle ? (
            <p className="mt-2 text-[13px] text-[var(--muted)]">{subtitle}</p>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="border border-[var(--fg)] px-2 py-1 text-[11px]">
              {readableItemSourceKind(
                primaryItem?.source_kind ?? "photo_estimate",
              )}
            </span>
            <span className="border border-[var(--fg)] px-2 py-1 text-[11px]">
              черновик
            </span>
            {primaryItem?.calculation_method ? (
              <span className="border border-[var(--hairline)] px-2 py-1 text-[11px]">
                {readableCalculationMethod(primaryItem.calculation_method)}
              </span>
            ) : null}
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-[34px] leading-none">
            {formatKcalValue(estimation.suggested_totals.total_kcal)}
          </div>
          <div className="mt-1 text-[12px] text-[var(--fg)]">ккал</div>
        </div>
      </div>

      <div className="grid grid-cols-4 border-b border-[var(--hairline)] py-6">
        <DraftMacro
          label="углеводы"
          unit="г"
          value={estimation.suggested_totals.total_carbs_g}
        />
        <DraftMacro
          label="белки"
          unit="г"
          value={estimation.suggested_totals.total_protein_g}
        />
        <DraftMacro
          label="жиры"
          unit="г"
          value={estimation.suggested_totals.total_fat_g}
        />
        <DraftMacro
          label="клетчатка"
          unit="г"
          value={estimation.suggested_totals.total_fiber_g}
        />
      </div>

      {primaryBreakdown?.calculated_per_unit ? (
        <BreakdownBlock
          title="За 1 шт."
          rows={[
            ["масса", primaryBreakdown.net_weight_per_unit_g, "г", "macro"],
            [
              "углеводы",
              primaryBreakdown.calculated_per_unit.carbs_g,
              "г",
              "macro",
            ],
            [
              "белки",
              primaryBreakdown.calculated_per_unit.protein_g,
              "г",
              "macro",
            ],
            ["жиры", primaryBreakdown.calculated_per_unit.fat_g, "г", "macro"],
            [
              "клетчатка",
              primaryBreakdown.calculated_per_unit.fiber_g,
              "г",
              "macro",
            ],
            ["ккал", primaryBreakdown.calculated_per_unit.kcal, "ккал", "kcal"],
          ]}
        />
      ) : null}

      <BreakdownBlock
        title="Итого"
        rows={[
          ["количество", primaryBreakdown?.count_detected, "", "integer"],
          ["общая масса", primaryBreakdown?.total_weight_g, "г", "macro"],
          [
            "углеводы",
            primaryBreakdown?.calculated_total.carbs_g ??
              estimation.suggested_totals.total_carbs_g,
            "г",
            "macro",
          ],
          [
            "белки",
            primaryBreakdown?.calculated_total.protein_g ??
              estimation.suggested_totals.total_protein_g,
            "г",
            "macro",
          ],
          [
            "жиры",
            primaryBreakdown?.calculated_total.fat_g ??
              estimation.suggested_totals.total_fat_g,
            "г",
            "macro",
          ],
          [
            "клетчатка",
            primaryBreakdown?.calculated_total.fiber_g ??
              estimation.suggested_totals.total_fiber_g,
            "г",
            "macro",
          ],
          [
            "ккал",
            primaryBreakdown?.calculated_total.kcal ??
              estimation.suggested_totals.total_kcal,
            "ккал",
            "kcal",
          ],
        ]}
      />

      <section className="grid grid-cols-2 gap-3 border-b border-[var(--hairline)] py-6">
        <div>
          <h3 className="mb-3 text-[12px] uppercase tracking-[0.02em]">
            Источник
          </h3>
          <div className="min-h-16 bg-[rgba(255,255,255,0.42)] p-4">
            <div className="text-[15px] text-[var(--fg)]">
              {readableItemSourceKind(
                primaryItem?.source_kind ?? "photo_estimate",
              )}
            </div>
            <div className="mt-2 text-[12px] text-[var(--muted)]">
              {readableCalculationMethod(primaryItem?.calculation_method) ||
                "черновик Gemini"}
            </div>
          </div>
        </div>
        <div>
          <h3 className="mb-3 text-[12px] uppercase tracking-[0.02em]">
            Уверенность
          </h3>
          <div className="min-h-16 bg-[rgba(255,255,255,0.42)] p-4">
            <div className="font-mono text-[28px] leading-none">
              {confidenceLabel}
            </div>
            <div className="mt-2 text-[12px] text-[var(--muted)]">
              {primaryItem?.confidence_reason ?? "нет данных"}
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-[var(--hairline)] py-6">
        <h3 className="text-[13px] uppercase tracking-[0.02em]">позиции</h3>
        <div className="mt-4 grid gap-4">
          {items.map((item, index) => (
            <div
              className={`grid gap-3 border-l-4 border-[var(--hairline)] bg-[rgba(255,255,255,0.35)] p-4 ${itemConfidenceTone(
                item.confidence,
              )}`}
              key={`${item.name}-${index}`}
            >
              <div className="grid grid-cols-[72px_1fr] gap-3">
                <EstimateItemPhoto item={item} photos={sourcePhotos} />
                <div className="min-w-0">
                  <input
                    aria-label={`Название оцененной позиции ${index + 1}`}
                    className="w-full border-b border-[var(--hairline)] bg-transparent pb-2 text-[15px] outline-none"
                    onChange={(event) =>
                      onChangeItem(index, { name: event.target.value })
                    }
                    value={item.name}
                  />
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.04em] text-[var(--muted)]">
                    <span>{estimateItemTypeLabel(item)}</span>
                    <span>{readableItemSourceKind(item.source_kind)}</span>
                    <span>
                      фото: {estimatePhotoUsageText(item, sourcePhotos)}
                    </span>
                    <span>
                      уверенность{" "}
                      {item.confidence === null || item.confidence === undefined
                        ? "--"
                        : item.confidence.toFixed(2)}
                    </span>
                  </div>
                  {item.confidence_reason ? (
                    <p className="mt-2 text-[12px] text-[var(--muted)]">
                      {item.confidence_reason}
                    </p>
                  ) : null}
                </div>
              </div>
              <div className="grid grid-cols-6 gap-2">
                {(
                  [
                    "grams",
                    "carbs_g",
                    "kcal",
                    "protein_g",
                    "fat_g",
                    "fiber_g",
                  ] as const
                ).map((field) => (
                  <label className="grid gap-1" key={field}>
                    <span className="text-[10px] uppercase tracking-[0.04em] text-[var(--muted)]">
                      {field
                        .replace("grams", "масса")
                        .replace("carbs_g", "углеводы")
                        .replace("protein_g", "белки")
                        .replace("fat_g", "жиры")
                        .replace("fiber_g", "клетчатка")
                        .replace("kcal", "ккал")}
                    </span>
                    <input
                      aria-label={`${item.name}: оценка ${field}`}
                      className="border border-[var(--hairline)] bg-[var(--surface)] px-2 py-1 text-right font-mono text-[13px]"
                      onChange={(event) => {
                        const value = event.target.value;
                        onChangeItem(index, {
                          [field]:
                            field === "grams" && value === ""
                              ? null
                              : Number(value) || 0,
                        });
                      }}
                      type="number"
                      value={item[field] ?? ""}
                    />
                  </label>
                ))}
              </div>
              <EstimateItemReview item={item} />
            </div>
          ))}
        </div>
      </section>

      <section className="border-b border-[var(--hairline)] py-6">
        <h3 className="text-[13px] uppercase tracking-[0.02em]">Данные</h3>
        <div className="mt-4 grid gap-2">
          {evidenceRows.length ? (
            evidenceRows
              .slice(0, 8)
              .map((label) => <EvidenceLine key={label} label={label} />)
          ) : (
            <p className="text-[13px] text-[var(--muted)]">данных нет</p>
          )}
        </div>
      </section>

      {import.meta.env.DEV && estimation.raw_gemini_response ? (
        <details className="border-b border-[var(--hairline)] py-6">
          <summary className="cursor-pointer text-[13px] uppercase tracking-[0.02em]">
            Показать raw Gemini
          </summary>
          <pre className="mt-4 max-h-72 overflow-auto whitespace-pre-wrap border border-[var(--hairline)] bg-[var(--surface)] p-3 text-[11px]">
            {JSON.stringify(estimation.raw_gemini_response, null, 2)}
          </pre>
        </details>
      ) : null}

      <section className="border-b border-[var(--hairline)] py-6">
        <h3 className="text-[13px] uppercase tracking-[0.02em]">
          Как посчитано
        </h3>
        <div className="mt-4 grid gap-2">
          {primaryBreakdown?.calculation_steps?.length ? (
            primaryBreakdown.calculation_steps.map((step) => (
              <EvidenceLine key={step} label={step} />
            ))
          ) : (
            <p className="text-[13px] text-[var(--muted)]">
              расчётная история недоступна
            </p>
          )}
        </div>
      </section>

      <section className="border-b border-[var(--hairline)] py-6">
        <h3 className="text-[13px] uppercase tracking-[0.02em]">Допущения</h3>
        {assumptions.length ? (
          <ul className="mt-3 grid gap-2 pl-5 text-[13px]">
            {assumptions.slice(0, 6).map((assumption, index) => (
              <li className="list-disc" key={`${assumption}-${index}`}>
                {assumption}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-[13px] text-[var(--muted)]">Допущений нет.</p>
        )}
      </section>

      {edited ? (
        <div className="border-b border-[var(--hairline)] py-4">
          <StatusText>backend пересчитает при сохранении</StatusText>
        </div>
      ) : null}

      <div className="sticky bottom-0 mt-auto grid gap-3 border-t border-[var(--hairline)] bg-[var(--bg)] py-4">
        <Button
          disabled={saving}
          icon={<Check size={16} />}
          onClick={onSave}
          variant="primary"
        >
          Сохранить
        </Button>
        <Button
          disabled={saving}
          icon={<X size={16} />}
          onClick={onDiscard}
          variant="danger"
        >
          Отменить
        </Button>
        <p className="pt-5 text-[11px] text-[var(--muted)]">
          Это оценка, не медицинская рекомендация.
        </p>
      </div>
    </div>
  );
}

function SourcePhotoPreview({
  photos,
}: {
  photos: NonNullable<EstimateMealResponse["source_photos"]>;
}) {
  const first = photos[0];
  if (!first) {
    return (
      <div className="flex h-52 items-center justify-center border border-[var(--hairline)] bg-[var(--surface)] text-[var(--muted)]">
        <ImagePlus size={28} strokeWidth={1.6} />
      </div>
    );
  }
  return <SourcePhotoImage photoId={first.id} size="large" />;
}

function SourcePhotoThumb({ photoId }: { photoId: string }) {
  return <SourcePhotoImage photoId={photoId} size="thumb" />;
}

function SourcePhotosDebug({ photos }: { photos: EstimateSourcePhoto[] }) {
  if (!photos.length) {
    return null;
  }
  return (
    <details className="border-b border-[var(--hairline)] py-5">
      <summary className="cursor-pointer text-[13px] uppercase tracking-[0.02em]">
        Фото, отправленные на оценку
      </summary>
      <div className="mt-4 grid gap-3">
        {photos.map((photo) => (
          <div
            className="grid grid-cols-[56px_1fr] items-center gap-3 border-b border-[var(--hairline)] pb-3"
            key={photo.id}
          >
            <SourcePhotoImage
              alt={`Фото ${photo.index}`}
              photoId={photo.id}
              size="thumb"
            />
            <div className="min-w-0">
              <div className="text-[13px] text-[var(--fg)]">
                Фото {photo.index}
              </div>
              <div className="truncate text-[11px] text-[var(--muted)]">
                {photo.original_filename ?? photo.id}
              </div>
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

function EstimateItemPhoto({
  item,
  photos,
}: {
  item: MealItemCreate;
  photos: EstimateSourcePhoto[];
}) {
  const primaryPhotoId = estimatePrimaryPhotoId(item);
  const fallbackByIndex = estimateSourcePhotoIndices(item)
    .map((index) => photos.find((photo) => photo.index === index)?.id)
    .find(Boolean);
  const photoId = primaryPhotoId ?? fallbackByIndex;

  if (!photoId) {
    return (
      <div className="flex h-[72px] w-[72px] items-center justify-center border border-[var(--hairline)] bg-[var(--surface)] text-[var(--muted)]">
        <ImagePlus size={18} strokeWidth={1.6} />
      </div>
    );
  }

  return (
    <SourcePhotoImage alt={`${item.name} фото`} photoId={photoId} size="item" />
  );
}

function EstimateItemReview({ item }: { item: MealItemCreate }) {
  const evidenceRows = estimateItemEvidenceRows(item);
  const assumptions = estimateItemAssumptions(item);
  const warnings = (item.warnings ?? []).map((warning) =>
    typeof warning === "string"
      ? warning
      : String(
          (warning as { message?: unknown }).message ?? JSON.stringify(warning),
        ),
  );

  return (
    <div className="grid gap-4 border-t border-[var(--hairline)] pt-3">
      {evidenceRows.length ? (
        <div>
          <h4 className="text-[11px] uppercase tracking-[0.05em] text-[var(--muted)]">
            данные
          </h4>
          <div className="mt-2 grid gap-1">
            {evidenceRows.slice(0, 4).map((label) => (
              <EvidenceLine key={label} label={label} />
            ))}
          </div>
        </div>
      ) : null}
      {assumptions.length ? (
        <div>
          <h4 className="text-[11px] uppercase tracking-[0.05em] text-[var(--muted)]">
            допущения
          </h4>
          <ul className="mt-2 grid gap-1 pl-5 text-[12px] text-[var(--fg)]">
            {assumptions.slice(0, 4).map((assumption, index) => (
              <li className="list-disc" key={`${assumption}-${index}`}>
                {assumption}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {warnings.length ? (
        <div>
          <h4 className="text-[11px] uppercase tracking-[0.05em] text-[var(--muted)]">
            предупреждения
          </h4>
          <div className="mt-2 grid gap-1">
            {warnings.map((warning) => (
              <EvidenceLine key={warning} label={warning} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SourcePhotoImage({
  alt = "фото к оценке",
  photoId,
  size,
}: {
  alt?: string;
  photoId: string;
  size: "large" | "thumb" | "item";
}) {
  const config = useApiConfig();
  const photoFile = useQuery({
    queryKey: ["estimate-photo-file", photoId, config.baseUrl, config.token],
    queryFn: () => apiClient.getPhotoFile(config, photoId),
    enabled: Boolean(config.token.trim() && photoId),
  });
  const photoObjectUrl = useBlobObjectUrl(photoFile.data);

  const className =
    size === "large"
      ? "h-52 w-full object-cover"
      : size === "item"
        ? "h-[72px] w-[72px] object-cover"
        : "h-14 w-full object-cover";

  return (
    <div className="overflow-hidden border border-[var(--hairline)] bg-[var(--surface)]">
      {photoObjectUrl ? (
        <img alt={alt} className={className} src={photoObjectUrl} />
      ) : (
        <div
          className={`flex items-center justify-center text-[11px] uppercase tracking-[0.06em] text-[var(--muted)] ${
            size === "large" ? "h-52" : size === "item" ? "h-[72px]" : "h-14"
          }`}
        >
          {photoFile.isError ? "фото недоступно" : "фото"}
        </div>
      )}
    </div>
  );
}

type BreakdownRow = [
  label: string,
  value: number | null | undefined,
  unit: string,
  kind: "macro" | "kcal" | "integer",
];

function BreakdownBlock({
  rows,
  title,
}: {
  rows: BreakdownRow[];
  title: string;
}) {
  const visibleRows = rows.filter(
    ([, value]) => value !== null && value !== undefined,
  );
  if (!visibleRows.length) {
    return null;
  }
  return (
    <section className="border-b border-[var(--hairline)] py-6">
      <h3 className="text-[13px] uppercase tracking-[0.02em]">{title}</h3>
      <div className="mt-4 grid gap-2">
        {visibleRows.map(([label, value, unit, kind]) => (
          <div
            className="grid grid-cols-[1fr_auto] border-b border-[var(--hairline)] py-2 text-[13px]"
            key={`${title}-${label}`}
          >
            <span className="text-[var(--muted)]">{label}</span>
            <span className="font-mono text-[var(--fg)]">
              {kind === "kcal"
                ? formatKcalValue(value)
                : kind === "integer"
                  ? Math.round(Number(value))
                  : formatMacroValue(value)}
              {unit ? <span className="ml-1 text-[11px]">{unit}</span> : null}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function EvidenceLine({ label }: { label: string }) {
  return (
    <div className="border-b border-[var(--hairline)] py-2 text-[13px] text-[var(--fg)]">
      {label}
    </div>
  );
}

function DraftMacro({
  label,
  unit,
  value,
}: {
  label: string;
  unit: string;
  value: number;
}) {
  return (
    <div className="text-center">
      <div className="font-mono text-[24px] leading-none">
        {numberLabel(value)}
      </div>
      <div className="mt-2 text-[11px] uppercase tracking-[0.02em]">
        {label} <span className="lowercase text-[var(--muted)]">{unit}</span>
      </div>
    </div>
  );
}
