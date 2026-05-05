import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Camera, Check, ImagePlus, X } from "lucide-react";
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
  SelectedMealPanel,
  evidenceLabelsForItem,
  numberLabel,
  readableCalculationMethod,
  readableItemSourceKind,
} from "../meals/MealLedger";
import {
  useCreateMealFromItemWeight,
  useUpdateMealItemWeight,
  useUpdateMealName,
  useUpdateMealTime,
} from "../meals/useMealMutations";
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
    return "border-l-[var(--warn)]";
  }
  if (confidence > 0.85) {
    return "border-l-[var(--good)]";
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

  const invalidateMeals = () => {
    queryClient.invalidateQueries({ queryKey: ["meals"] });
    queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
    queryClient.invalidateQueries({ queryKey: ["timeline"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

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

  const updateMealTime = useUpdateMealTime();

  const updateMealName = useUpdateMealName();
  const createFromWeight = useCreateMealFromItemWeight();
  const updateItemWeight = useUpdateMealItemWeight();

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
  const dayNavLabel = isViewingToday ? "Сегодня" : formatDayTitle(selectedDate);

  return (
    <div
      className="gt-page"
      style={{ minHeight: "100%", position: "relative" }}
      onDragOver={(event) => event.preventDefault()}
      onDrop={handleDrop}
      onPaste={handlePaste}
    >
      <div
        style={{
          display: "flex",
          minHeight: "100%",
          transition: "padding-right 0.2s ease-out",
          paddingRight: panelMode ? 420 : 0,
        }}
      >
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          <header style={{ flexShrink: 0 }}>
            <div className="gt-crumbs" style={{ marginBottom: 4 }}>
              <span>{formatDayWeekday(selectedDate)}</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 24, marginBottom: 24 }}>
              <h1 className="gt-h1" style={{ fontFamily: "var(--mono)", fontSize: 36 }}>
                {formatDayTitle(selectedDate)}
              </h1>
              <div style={{ display: "flex", alignItems: "center", gap: 6, paddingBottom: 6 }}>
                <button className="btn icon" onClick={handleGoToPreviousDay} aria-label="Предыдущий день" type="button">{"<"}</button>
                <button className="btn" onClick={handleGoToToday} type="button">{dayNavLabel}</button>
                <button className="btn icon" aria-label="Следующий день" disabled={isViewingToday} onClick={handleGoToNextDay} type="button">{">"}</button>
              </div>
            </div>
            <DailySummary totals={dayTotals} />
            <div className="ns-strip">
              <span className="dot-marker" style={{ background: nightscoutDay.data?.connected ? "var(--good)" : "var(--hairline)" }} />
              <span>{nightscoutDay.data?.connected ? "Nightscout подключён" : "Nightscout не подключён"}</span>
              {nightscoutDay.data?.configured ? (
                <>
                  <span style={{ fontSize: 11, color: "var(--ink-3)" }}>несинхронизировано: <b className="mono" style={{ color: "var(--ink)", fontWeight: 500 }}>{nightscoutDay.data.unsynced_meals_count}</b></span>
                  {nightscoutDay.data.last_sync_at ? (
                    <span style={{ fontSize: 11, color: "var(--ink-3)" }}>последняя синхронизация:{" "}
                      {new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(new Date(nightscoutDay.data.last_sync_at))}
                    </span>
                  ) : null}
                </>
              ) : (
                <a className="btn-link" href="/settings">Настроить</a>
              )}
              <span className="spacer" />
              <button className="btn" disabled={!nightscoutDay.data?.configured || !nightscoutDay.data?.connected || !nightscoutDay.data?.unsynced_meals_count || syncTodayNightscout.isPending}
                onClick={() => syncTodayNightscout.mutate()} type="button">
                {syncTodayNightscout.isPending ? "Отправляю..." : "Отправить день в Nightscout"}
              </button>
            </div>
            {syncTodayNightscout.data ? (
              <div className="ns-strip" style={{ marginTop: 0, borderTop: "none", borderTopLeftRadius: 0, borderTopRightRadius: 0 }}>
                <span style={{ width: "100%", fontSize: 12, color: "var(--ink)" }}>
                  Отправлено: {syncTodayNightscout.data.sent_count}, пропущено: {syncTodayNightscout.data.skipped_count}, ошибок: {syncTodayNightscout.data.failed_count}
                </span>
              </div>
            ) : null}
          </header>

          <section style={{ marginTop: 6, flex: 1, minHeight: 0 }}>
            <div className="card" style={{ padding: "8px 16px" }}>
            {!config.token.trim() ? <EmptyLog message="Укажите адрес backend и токен в настройках." /> : null}
            {config.token.trim() && meals.isLoading ? <EmptyLog message="Загружаю еду." /> : null}
            {config.token.trim() && meals.isSuccess && !todayMeals.length ? <EmptyLog message={emptyDayMessage} /> : null}
            {todayMeals.map((meal) => (
              <MealRow key={meal.id} meal={meal} selected={selectedMealId === meal.id} onToggle={() => handleMealToggle(meal)} />
            ))}
            </div>
          </section>

          <section style={{ flexShrink: 0, paddingTop: 14 }}>
            <div style={{ marginBottom: 8, display: "flex", flexWrap: "wrap", gap: 6 }}>
              {chips.map((chip, index) => (
                <div className="tag accent" key={`${chip.token}-${index}`} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <button
                    aria-label={chip.token}
                    onClick={() => setChips((current) => current.filter((_, ci) => ci !== index))}
                    type="button"
                  >
                    {chip.token} <span style={{ color: "var(--ink-3)" }}>×</span>
                  </button>
                  {chip.kind === "product" ? (
                    <label style={{ display: "flex", alignItems: "center", gap: 4, textTransform: "none", letterSpacing: 0, color: "var(--ink-3)" }}>
                      <span>Кол-во</span>
                      <input
                        aria-label={`Количество ${chip.display_name}`}
                        style={{ width: 40, height: 20, border: "1px solid var(--hairline-2)", background: "var(--bg)", padding: "0 4px", textAlign: "right", fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink)", outline: "none" }}
                        min="0.1" step="0.5" type="number" value={chip.quantity ?? ""}
                        onChange={(event) => {
                          const rawValue = event.target.value;
                          const value = Number(event.target.value);
                          setChips((current) => current.map((c, ci) => ci === index ? { ...c, quantity: rawValue === "" ? undefined : Number.isFinite(value) && value > 0 ? value : 1 } : c));
                        }}
                      />
                      <span>шт</span>
                    </label>
                  ) : null}
                </div>
              ))}
            </div>

            {estimatePhase !== "idle" ? (
              <div className="lbl" style={{ marginBottom: 8, color: "var(--accent)" }}>
                Оцениваю фото... {estimatePhaseText[estimatePhase]}
              </div>
            ) : null}

            <div className="row gap-12" style={{ alignItems: "center" }}>
              <div className="input-bar" style={{ flex: 1, borderColor: panelMode === "autocomplete" ? "var(--ink)" : "var(--hairline-2)" }}>
                <button className="btn icon" style={{ border: "none", background: "transparent" }} type="button" onClick={() => commandInputRef.current?.focus()}>
                  <ImagePlus size={15} />
                </button>
                <span className="mono" style={{ color: "var(--ink-4)", flexShrink: 0 }}>{">"}</span>
                <input
                  id="command-input"
                  onChange={(event) => { setInput(event.target.value); setAutocompleteDismissedToken(""); }}
                  onKeyDown={handleKeyDown}
                  placeholder="bk:whopper · введите еду или используйте префикс bk: / mc:"
                  ref={commandInputRef}
                  value={input}
                />
                {input ? (
                  <button aria-label="Очистить команду" className="btn icon" style={{ border: "none", background: "transparent", color: "var(--ink-3)" }}
                    onClick={() => { setInput(""); setAutocompleteDismissedToken(""); }} type="button"><X size={14} /></button>
                ) : null}
                <button className="send-btn" aria-label="Записать" disabled={createMeal.isPending} onClick={handleSubmit} type="button">
                  <ArrowRight size={16} />
                </button>
              </div>
              <button className="btn" type="button" onClick={() => { setPhotoPanelOpen(true); imageInputRef.current?.click(); }}>
                <Camera size={14} /> Фото
              </button>
              <input
                accept="image/jpeg,image/png,image/webp" aria-label="Выбрать фото" className="sr-only" multiple
                onChange={(event) => { if (event.target.files?.length) { addFilesToPendingPhotos(event.target.files, "file_picker"); event.target.value = ""; } }}
                ref={imageInputRef} type="file"
              />
            </div>
            <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 8, marginLeft: 4 }}>
              подсказки: <span className="mono">bk:</span> Burger King · <span className="mono">mc:</span> McDonald's · перетащите фото — Gemini оценит макросы
            </div>
          </section>
        </div>

        {panelMode ? (
          <div className="gt-rightpanel" style={{ position: "fixed", right: 0, top: 0, bottom: 0, zIndex: 10 }}>
            <button onClick={clearActivePanelState} style={{ position: "absolute", top: 10, right: 10, background: "none", border: "none", cursor: "pointer", color: "var(--ink-3)" }}>
              <X size={16} />
            </button>
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
                createFromWeightPending={createFromWeight.isPending}
                deletePending={deleteMeal.isPending}
                meal={selectedMeal}
                onCreateFromWeight={(item, grams) =>
                  createFromWeight.mutate(
                    { grams, itemId: item.id },
                    { onSuccess: (meal) => setSelectedMealId(meal.id) },
                  )
                }
                onDelete={(meal) => deleteMeal.mutate(meal.id)}
                onUpdateItemWeight={(item, grams) =>
                  updateItemWeight.mutate({ grams, itemId: item.id })
                }
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
                updateWeightPending={updateItemWeight.isPending}
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
          </div>
        ) : null}
      </div>
    </div>
  );
}

function DailySummary({ totals }: { totals: DayTotals }) {
  const carbPct = Math.round((totals.carbs / 225) * 100);
  const kcalPct = Math.round((totals.kcal / 2200) * 100);
  return (
    <section className="kpi" style={{ marginBottom: 14 }}>
      <div>
        <div className="lbl">углеводы</div>
        <div className="kpi-val" style={{ marginTop: 8 }}>{numberLabel(totals.carbs)}<span className="u">г</span></div>
        <div className="pbar accent" style={{ marginTop: 10 }}><i style={{ width: `${Math.min(100, carbPct)}%` }} /></div>
        <div className="kpi-sub">цель 225 г · <span className="mono">{carbPct}%</span></div>
      </div>
      <div>
        <div className="lbl">ккал</div>
        <div className="kpi-val" style={{ marginTop: 8 }}>{numberLabel(totals.kcal)}<span className="u">ккал</span></div>
        <div className="pbar good" style={{ marginTop: 10 }}><i style={{ width: `${Math.min(100, kcalPct)}%` }} /></div>
        <div className="kpi-sub">цель 2200 · <span className="mono">{kcalPct}%</span></div>
      </div>
      <div>
        <div className="lbl">белки · жиры · клетчатка</div>
        <div className="row gap-12" style={{ marginTop: 8, alignItems: "baseline" }}>
          <span className="mono" style={{ fontSize: 20, fontWeight: 500 }}>{numberLabel(totals.protein)}<span style={{ fontSize: 10, color: "var(--ink-3)", marginLeft: 2 }}>г Б</span></span>
          <span className="mono" style={{ fontSize: 20, fontWeight: 500 }}>{numberLabel(totals.fat)}<span style={{ fontSize: 10, color: "var(--ink-3)", marginLeft: 2 }}>г Ж</span></span>
          <span className="mono" style={{ fontSize: 20, fontWeight: 500 }}>{numberLabel(totals.fiber)}<span style={{ fontSize: 10, color: "var(--ink-3)", marginLeft: 2 }}>г Кл</span></span>
        </div>
        <div className="kpi-sub" style={{ marginTop: 10 }}>дневная сводка</div>
      </div>
      <div>
        <div className="lbl">ккал / TDEE</div>
        <div className="kpi-val" style={{ marginTop: 8 }}>
          {numberLabel(totals.kcal)}<span className="u">ккал</span>
        </div>
        <div className="kpi-sub" style={{ marginTop: 10 }}>дневная цель 2200</div>
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
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div className="hairline" style={{ paddingBottom: 16 }}>
        <div className="lbl">фото к оценке</div>
        <h2 style={{ marginTop: 8 }}>{photos.length ? `${photos.length} фото` : "добавьте фото"}</h2>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
        {!photos.length ? (
          <div className="hairline" style={{ padding: "16px 0" }}>
            <p style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.5 }}>Перетащите фото из Связи с телефоном или Проводника Windows</p>
            <p style={{ marginTop: 8, fontSize: 12, color: "var(--ink-3)", lineHeight: 1.5 }}>Фото не отправляются в облако, они загружаются только в ваш локальный backend</p>
          </div>
        ) : null}

        {photos.map((photo) => (
          <div className="t-row" key={photo.id}>
            <img alt={photo.name} style={{ width: 44, height: 44, borderRadius: 3, objectFit: "cover", border: "1px solid var(--hairline)" }} src={photo.previewUrl} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{photo.name}</div>
              <div className="lbl" style={{ marginTop: 2 }}>{photoSourceLabels[photo.source]}{photo.mimeType ? ` / ${photo.mimeType}` : ""}</div>
            </div>
            <button className="btn-link" style={{ color: "var(--warn)" }} onClick={() => onRemove(photo.id)} type="button">Удалить</button>
          </div>
        ))}
      </div>

      {estimating ? (
        <div className="lbl" style={{ padding: "12px 0", color: "var(--accent)" }}>Оцениваю фото...</div>
      ) : null}
      {error ? (
        <p style={{ padding: "12px 0", fontSize: 13, color: "var(--warn)" }}>{error}</p>
      ) : null}

      <div className="hairline" style={{ paddingTop: 12, marginTop: "auto" }}>
        <div className="field" style={{ marginBottom: 12 }}>
          <label>Контекст для фото</label>
          <textarea
            aria-label="Контекст для фото"
            disabled={estimating}
            maxLength={1200}
            onChange={(event) => onChangeContextNote(event.target.value)}
            placeholder="например: 100 г варёного риса, половина тортильи, без соуса"
            value={contextNote}
          />
          <span style={{ fontSize: 10, color: "var(--ink-3)" }}>Этот текст отправляется только в backend как подсказка для оценки.</span>
        </div>
        <div className="field" style={{ marginBottom: 12 }}>
          <label>Модель оценки</label>
          <select
            aria-label="Модель оценки фото"
            style={{ height: 32, border: "1px solid var(--hairline-2)", background: "var(--surface)", padding: "0 8px", fontFamily: "var(--mono)", fontSize: 12, borderRadius: "var(--radius)", color: "var(--ink)", outline: "none" }}
            disabled={estimating}
            onChange={(event) => onChangeModel(event.target.value as EstimateModel)}
            value={estimateModel}
          >
            <option value="default">По умолчанию backend</option>
            <option value="gemini-3-flash-preview">Gemini 3 Flash Preview</option>
            <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
            <option value="gemini-3.1-flash-lite-preview">Gemini 3.1 Flash Lite</option>
          </select>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn dark" disabled={!photos.length || estimating} onClick={onEstimate} type="button">
            <ImagePlus size={14} />{error ? "Повторить" : "Оценить"}
          </button>
          <button className="btn" disabled={!photos.length || estimating} onClick={onClear} type="button">Очистить</button>
        </div>
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
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="hairline" style={{ paddingBottom: 16 }}>
        <div className="lbl">автозаполнение</div>
        <h2 style={{ marginTop: 8, wordBreak: "break-all" }}>{token}</h2>
      </div>

      <div className="hairline" style={{ padding: "10px 0" }}>
        <div className="lbl">частые</div>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden" }}>
        {loading ? (
          <div className="t-row"><StatusText>Поиск</StatusText></div>
        ) : null}
        {results.length ? (
          results.map((result, index) => (
            <button
              className={`ac-item ${activeIndex === index ? "selected" : ""}`}
              key={`${result.kind}-${result.id ?? result.token}`}
              onClick={() => onSelect(result)}
              type="button"
              style={{ width: "100%", textAlign: "left" }}
            >
              <div style={{ width: 36, height: 36, borderRadius: 3, background: "var(--shade)", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <FoodImage
                  alt={`${result.display_name} фото`}
                  fit="contain"
                  src={result.image_url}
                />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{result.display_name}</div>
                <div style={{ fontSize: 11, color: "var(--ink-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {suggestionKindLabel(result)} · {result.subtitle ?? result.token}
                </div>
                <div style={{ marginTop: 6, display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" }}>
                  <AutocompleteMacro value={result.carbs_g} unit="У" />
                  <AutocompleteMacro value={result.protein_g} unit="Б" />
                  <AutocompleteMacro value={result.fat_g} unit="Ж" />
                  <span className="mono" style={{ fontSize: 13 }}>{formatKcal(result.kcal)}</span>
                </div>
              </div>
            </button>
          ))
        ) : !loading ? (
          <p className="t-row" style={{ fontSize: 13, color: "var(--ink-3)" }}>Ничего не найдено</p>
        ) : null}
      </div>
      <div className="hairline" style={{ paddingTop: 10 }}>
        <button className="btn" style={{ width: "100%", justifyContent: "space-between" }} type="button">
          <span>Все результаты для «{token}»</span>
          <span className="mono">→</span>
        </button>
      </div>
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
        <p className="text-[12px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
          Результат оценки
        </p>
        <h2 className="mt-3 text-[30px] leading-none text-[var(--ink)]">
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
                <div className="flex h-[72px] w-[72px] items-center justify-center border border-[var(--hairline)] bg-[var(--surface)] text-[var(--ink-3)]">
                  <ImagePlus size={20} strokeWidth={1.5} />
                </div>
              )}
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
                  {index + 1}. Фото / черновик
                </div>
                <h3 className="mt-2 truncate text-[20px] leading-tight text-[var(--ink)]">
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
          <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--ink-3)]">
            черновик
          </p>
          <h2 className="mt-3 text-[26px] leading-tight text-[var(--ink)]">
            {primaryItem?.name ?? "Еда по фото"}
          </h2>
          {subtitle ? (
            <p className="mt-2 text-[13px] text-[var(--ink-3)]">{subtitle}</p>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="border border-[var(--ink)] px-2 py-1 text-[11px]">
              {readableItemSourceKind(
                primaryItem?.source_kind ?? "photo_estimate",
              )}
            </span>
            <span className="border border-[var(--ink)] px-2 py-1 text-[11px]">
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
          <div className="mt-1 text-[12px] text-[var(--ink)]">ккал</div>
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
            <div className="text-[15px] text-[var(--ink)]">
              {readableItemSourceKind(
                primaryItem?.source_kind ?? "photo_estimate",
              )}
            </div>
            <div className="mt-2 text-[12px] text-[var(--ink-3)]">
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
            <div className="mt-2 text-[12px] text-[var(--ink-3)]">
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
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.04em] text-[var(--ink-3)]">
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
                    <p className="mt-2 text-[12px] text-[var(--ink-3)]">
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
                    <span className="text-[10px] uppercase tracking-[0.04em] text-[var(--ink-3)]">
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
            <p className="text-[13px] text-[var(--ink-3)]">данных нет</p>
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
            <p className="text-[13px] text-[var(--ink-3)]">
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
          <p className="mt-3 text-[13px] text-[var(--ink-3)]">Допущений нет.</p>
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
        <p className="pt-5 text-[11px] text-[var(--ink-3)]">
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
      <div className="flex h-52 items-center justify-center border border-[var(--hairline)] bg-[var(--surface)] text-[var(--ink-3)]">
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
              <div className="text-[13px] text-[var(--ink)]">
                Фото {photo.index}
              </div>
              <div className="truncate text-[11px] text-[var(--ink-3)]">
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
      <div className="flex h-[72px] w-[72px] items-center justify-center border border-[var(--hairline)] bg-[var(--surface)] text-[var(--ink-3)]">
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
          <h4 className="text-[11px] uppercase tracking-[0.05em] text-[var(--ink-3)]">
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
          <h4 className="text-[11px] uppercase tracking-[0.05em] text-[var(--ink-3)]">
            допущения
          </h4>
          <ul className="mt-2 grid gap-1 pl-5 text-[12px] text-[var(--ink)]">
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
          <h4 className="text-[11px] uppercase tracking-[0.05em] text-[var(--ink-3)]">
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
          className={`flex items-center justify-center text-[11px] uppercase tracking-[0.06em] text-[var(--ink-3)] ${
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
            <span className="text-[var(--ink-3)]">{label}</span>
            <span className="font-mono text-[var(--ink)]">
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
    <div className="border-b border-[var(--hairline)] py-2 text-[13px] text-[var(--ink)]">
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
        {label} <span className="lowercase text-[var(--ink-3)]">{unit}</span>
      </div>
    </div>
  );
}
