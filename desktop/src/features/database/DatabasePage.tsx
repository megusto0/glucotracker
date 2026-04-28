import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Check, Copy, FileUp, Plus, Search } from "lucide-react";
import { type DragEvent, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient, type DatabaseItemResponse } from "../../api/client";
import { FoodImage } from "../../components/FoodImage";
import { Button } from "../../design/primitives/Button";
import { RightPanel } from "../meals/MealLedger";
import { useApiConfig } from "../settings/settingsStore";

type PanelMode = "detail" | "import" | "manual" | null;

const sourceOptions = [
  { label: "Все источники", value: "all" },
  { label: "BK", value: "bk" },
  { label: "MC", value: "mc" },
  { label: "Rostic's", value: "rostics" },
  { label: "Вкусно и точка", value: "vit" },
  { label: "Домашнее", value: "home" },
  { label: "Продукты", value: "products" },
  { label: "Ручное", value: "manual" },
];

const typeOptions = [
  { label: "Все", value: "all" },
  { label: "Шаблоны", value: "patterns" },
  { label: "Продукты", value: "products" },
  { label: "Рестораны", value: "restaurants" },
  { label: "Требуют проверки", value: "needs_review" },
  { label: "Проверено", value: "verified" },
  { label: "Без картинки", value: "missing_image" },
  { label: "Без БЖУ", value: "missing_nutrition" },
];

const sections = [
  { label: "Частые", type: "all" },
  { label: "Рестораны", type: "restaurants" },
  { label: "Продукты", type: "products" },
  { label: "Шаблоны", type: "patterns" },
  { label: "Требуют проверки", type: "needs_review" },
];

const nutrientLabels: Record<string, string> = {
  sodium_mg: "Натрий",
  caffeine_mg: "Кофеин",
  sugar_g: "Сахар",
  potassium_mg: "Калий",
  iron_mg: "Железо",
  calcium_mg: "Кальций",
  magnesium_mg: "Магний",
};

const kindLabels: Record<string, string> = {
  pattern: "шаблон",
  product: "продукт",
  restaurant: "ресторан",
};

const numberLabel = (value?: number | null) =>
  value === null || value === undefined ? "неизвестно" : Math.round(value);

const macroLabel = (value?: number | null, suffix = "") =>
  value === null || value === undefined ? "—" : `${Math.round(value)}${suffix}`;

const dateLabel = (iso?: string | null) =>
  iso
    ? new Intl.DateTimeFormat("ru-RU", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(iso))
    : "не использовалось";

const nutrientValue = (
  nutrients: DatabaseItemResponse["nutrients_json"],
  code: string,
) => {
  const raw = nutrients?.[code];
  if (raw === null || raw === undefined) {
    return null;
  }
  if (typeof raw === "number") {
    return { amount: raw, unit: code.endsWith("_g") ? "г" : "мг" };
  }
  if (typeof raw === "object" && "amount" in raw) {
    const entry = raw as { amount?: number | null; unit?: string | null };
    if (entry.amount === null || entry.amount === undefined) {
      return null;
    }
    return { amount: entry.amount, unit: entry.unit ?? "" };
  }
  return null;
};

const supportedImageTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
const supportedImageExtensions = [".jpg", ".jpeg", ".png", ".webp"];

const firstSupportedImageFile = (files?: FileList | File[] | null) =>
  Array.from(files ?? []).find((file) => {
    if (supportedImageTypes.has(file.type)) {
      return true;
    }
    const name = file.name.toLocaleLowerCase();
    return supportedImageExtensions.some((extension) => name.endsWith(extension));
  }) ?? null;

export function DatabasePage() {
  const config = useApiConfig();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [source, setSource] = useState("all");
  const [type, setType] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [panelMode, setPanelMode] = useState<PanelMode>(null);

  const database = useQuery({
    queryKey: ["database-items", q, source, type],
    queryFn: () =>
      apiClient.listDatabaseItems(config, {
        q,
        source,
        type,
        limit: 100,
      }),
    enabled: Boolean(config.token.trim()),
  });

  const items = database.data?.items ?? [];
  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId],
  );
  const uploadProductImage = useMutation({
    mutationFn: ({ file, productId }: { file: File; productId: string }) =>
      apiClient.uploadProductImage(config, productId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["database-items"] });
      queryClient.invalidateQueries({ queryKey: ["autocomplete"] });
      queryClient.invalidateQueries({ queryKey: ["meals"] });
      queryClient.invalidateQueries({ queryKey: ["feed-meals"] });
    },
  });

  const openDetail = (item: DatabaseItemResponse) => {
    setSelectedId(item.id);
    setPanelMode("detail");
  };

  return (
    <div className="h-screen overflow-hidden bg-[var(--bg)]">
      <div
        className={`flex h-screen min-h-0 flex-col px-12 py-10 transition-[padding] duration-200 ease-out ${
          panelMode ? "pr-[452px]" : ""
        }`}
      >
        <header className="shrink-0">
          <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
            продукты, шаблоны, рестораны, импорт
          </p>
          <h1 className="mt-4 text-[56px] font-normal leading-none text-[var(--fg)]">
            База
          </h1>
        </header>

        <section className="mt-9 grid shrink-0 grid-cols-[minmax(320px,1fr)_180px_200px_auto_auto] gap-3 border-y border-[var(--hairline)] py-4">
          <label className="grid gap-2">
            <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
              поиск
            </span>
            <span className="grid grid-cols-[20px_1fr] items-center gap-3 border-b border-[var(--hairline)] pb-2">
              <Search size={16} strokeWidth={1.7} />
              <input
                aria-label="Поиск по базе"
                className="bg-transparent text-[18px] outline-none"
                onChange={(event) => setQ(event.target.value)}
                placeholder="Поиск по базе"
                value={q}
              />
            </span>
          </label>

          <FilterSelect
            label="источник"
            onChange={setSource}
            options={sourceOptions}
            value={source}
          />
          <FilterSelect
            label="тип"
            onChange={setType}
            options={typeOptions}
            value={type}
          />
          <div className="flex items-end">
            <Button
              icon={<FileUp size={15} />}
              onClick={() => setPanelMode("import")}
            >
              Импорт
            </Button>
          </div>
          <div className="flex items-end">
            <Button
              icon={<Plus size={15} />}
              onClick={() => setPanelMode("manual")}
              variant="primary"
            >
              Добавить вручную
            </Button>
          </div>
        </section>

        <nav className="mt-7 flex shrink-0 flex-wrap gap-2">
          {sections.map((section) => (
            <button
              className={`border px-4 py-2 text-[12px] uppercase tracking-[0.06em] ${
                type === section.type
                  ? "border-[var(--fg)] bg-[var(--fg)] text-[var(--surface)]"
                  : "border-[var(--hairline)] bg-[var(--surface)] text-[var(--fg)]"
              }`}
              key={section.type}
              onClick={() => setType(section.type)}
              type="button"
            >
              {section.label}
            </button>
          ))}
        </nav>

        <section className="mt-7 min-h-0 flex-1 overflow-y-auto pr-2">
          {!config.token.trim() ? (
            <EmptyDatabaseState text="Укажите backend и токен в настройках." />
          ) : null}
          {database.isLoading ? (
            <EmptyDatabaseState text="Загружаю базу." />
          ) : null}
          {database.isError ? (
            <EmptyDatabaseState text="Не удалось загрузить базу." />
          ) : null}
          {database.isSuccess && !items.length ? (
            <EmptyDatabaseState text="В базе ничего не найдено." />
          ) : null}

          <div className="grid gap-0">
            {items.map((item) => (
              <DatabaseRow
                item={item}
                key={`${item.kind}-${item.id}`}
                onClick={() => openDetail(item)}
                selected={selectedId === item.id && panelMode === "detail"}
              />
            ))}
          </div>
        </section>
      </div>

      <RightPanel open={Boolean(panelMode)}>
        {panelMode === "detail" && selectedItem ? (
          <DatabaseDetailPanel
            imageUploadError={
              uploadProductImage.error instanceof Error
                ? uploadProductImage.error.message
                : null
            }
            imageUploadPending={uploadProductImage.isPending}
            item={selectedItem}
            onImageDrop={(file) =>
              uploadProductImage.mutate({ file, productId: selectedItem.id })
            }
            onUse={() => navigate("/")}
          />
        ) : null}
        {panelMode === "import" ? <ImportPanel /> : null}
        {panelMode === "manual" ? <ManualPanel /> : null}
      </RightPanel>
    </div>
  );
}

function FilterSelect({
  label,
  onChange,
  options,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  options: Array<{ label: string; value: string }>;
  value: string;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
        {label}
      </span>
      <select
        className="h-[37px] border-0 border-b border-[var(--hairline)] bg-transparent text-[13px] outline-none"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function DatabaseRow({
  item,
  onClick,
  selected,
}: {
  item: DatabaseItemResponse;
  onClick: () => void;
  selected: boolean;
}) {
  return (
    <button
      className={`grid w-full grid-cols-[48px_minmax(260px,1fr)_80px_80px_80px_116px_80px] items-center gap-4 border-b border-[var(--hairline)] py-4 text-left ${
        selected ? "bg-[rgba(255,255,255,0.55)]" : ""
      }`}
      onClick={onClick}
      type="button"
    >
      <FoodImage
        alt={`${item.display_name} фото`}
        className="h-12 w-12"
        fit="contain"
        src={item.image_url}
      />
      <span className="grid min-w-0 gap-1">
        <span className="truncate text-[16px] text-[var(--fg)]">
          {item.display_name}
        </span>
        <span className="truncate text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          {item.token ?? item.subtitle ?? kindLabels[item.kind]} ·{" "}
          {item.source_name ?? "локально"} ·{" "}
          {item.is_verified ? "проверено" : "не проверено"}
        </span>
      </span>
      <MacroCell value={item.carbs_g} unit="У" />
      <MacroCell value={item.protein_g} unit="Б" />
      <MacroCell value={item.fat_g} unit="Ж" />
      <span className="text-right font-mono text-[18px] text-[var(--fg)]">
        {macroLabel(item.kcal)}
        <span className="ml-1 text-[11px] text-[var(--muted)]">ккал</span>
      </span>
      <span className="text-right font-mono text-[13px] text-[var(--muted)]">
        {item.usage_count}
      </span>
    </button>
  );
}

function MacroCell({ unit, value }: { unit: string; value?: number | null }) {
  return (
    <span className="text-right font-mono text-[17px] text-[var(--fg)]">
      {macroLabel(value)}
      {value !== null && value !== undefined ? (
        <span className="ml-0.5 text-[10px] text-[var(--muted)]">{unit}</span>
      ) : null}
    </span>
  );
}

function DatabaseDetailPanel({
  imageUploadError,
  imageUploadPending,
  item,
  onImageDrop,
  onUse,
}: {
  imageUploadError?: string | null;
  imageUploadPending?: boolean;
  item: DatabaseItemResponse;
  onImageDrop?: (file: File) => void;
  onUse: () => void;
}) {
  const [dragActive, setDragActive] = useState(false);
  const [dropError, setDropError] = useState<string | null>(null);
  const metadata = item as DatabaseItemResponse & {
    source_file?: string | null;
    source_page?: number | null;
  };
  const canReplaceImage = item.kind === "product" && Boolean(onImageDrop);
  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (!canReplaceImage) {
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setDragActive(true);
  };
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    if (!canReplaceImage) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);
    setDropError(null);
    const file = firstSupportedImageFile(event.dataTransfer.files);
    if (!file) {
      setDropError("Этот формат фото пока не поддерживается.");
      return;
    }
    onImageDrop?.(file);
  };
  const handleFileSelect = (files: FileList | null) => {
    if (!canReplaceImage) {
      return;
    }
    setDropError(null);
    const file = firstSupportedImageFile(files);
    if (!file) {
      setDropError("Этот формат фото пока не поддерживается.");
      return;
    }
    onImageDrop?.(file);
  };
  const sourceConfidence =
    item.source_confidence === null || item.source_confidence === undefined
      ? "неизвестно"
      : String(item.source_confidence);
  const aliases = item.aliases ?? [];
  const qualityWarnings = item.quality_warnings ?? [];
  const knownNutrients = Object.entries(nutrientLabels)
    .map(([code, label]) => ({
      code,
      label,
      value: nutrientValue(item.nutrients_json, code),
    }))
    .filter((row) => row.value);

  return (
    <div
      aria-label="Карточка продукта"
      className={`relative flex h-full flex-col overflow-y-auto px-7 py-8 ${
        dragActive ? "bg-[rgba(255,255,255,0.72)]" : ""
      }`}
      onDragLeave={() => setDragActive(false)}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onDropCapture={handleDrop}
    >
      {dragActive && canReplaceImage ? (
        <div className="pointer-events-none absolute inset-3 z-10 flex items-center justify-center border border-dashed border-[var(--fg)] bg-[rgba(246,244,238,0.86)] text-center">
          <div>
            <p className="text-[12px] uppercase tracking-[0.08em] text-[var(--muted)]">
              заменить картинку
            </p>
            <p className="mt-3 text-[24px] leading-none text-[var(--fg)]">
              отпустите фото здесь
            </p>
          </div>
        </div>
      ) : null}
      <div className="grid grid-cols-[96px_1fr] gap-4 border-b border-[var(--hairline)] pb-7">
        <FoodImage
          alt={`${item.display_name} фото`}
          className="h-24 w-24"
          fit="contain"
          src={item.image_url}
        />
        <div className="min-w-0">
          <h2 className="text-[28px] leading-tight text-[var(--fg)]">
            {item.display_name}
          </h2>
          <p className="mt-2 text-[13px] text-[var(--muted)]">
            {item.token ?? item.subtitle ?? "локальная запись"}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Tag>{kindLabels[item.kind]}</Tag>
            <Tag>{item.is_verified ? "проверено" : "не проверено"}</Tag>
          </div>
          <div className="mt-4 border-t border-[var(--hairline)] pt-3 text-[12px] leading-relaxed text-[var(--muted)]">
            {item.kind === "product" ? (
              <>
                <p>Перетащите jpg, png или webp на эту правую карточку.</p>
                <p>Картинка заменится в Базе, Журнале и Истории.</p>
                <label className="mt-3 inline-flex cursor-pointer border border-[var(--hairline)] px-3 py-2 text-[11px] uppercase tracking-[0.06em] text-[var(--fg)]">
                  <input
                    accept="image/jpeg,image/png,image/webp"
                    aria-label="Заменить картинку продукта"
                    className="sr-only"
                    disabled={imageUploadPending}
                    onChange={(event) => handleFileSelect(event.target.files)}
                    type="file"
                  />
                  Выбрать картинку
                </label>
              </>
            ) : (
              <p>Замена картинки сейчас доступна только для продуктов.</p>
            )}
            {imageUploadPending ? (
              <p className="mt-2 uppercase tracking-[0.06em] text-[var(--fg)]">
                Загружаю картинку...
              </p>
            ) : null}
            {dropError || imageUploadError ? (
              <p className="mt-2 text-[var(--danger)]">
                {dropError ?? imageUploadError}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      <section className="border-b border-[var(--hairline)] py-6">
        <h3 className="text-[12px] uppercase tracking-[0.06em]">макросы</h3>
        <div className="mt-5 grid grid-cols-3 gap-x-4 gap-y-5">
          <Metric label="Углеводы" unit="г" value={item.carbs_g} />
          <Metric label="Белки" unit="г" value={item.protein_g} />
          <Metric label="Жиры" unit="г" value={item.fat_g} />
          <Metric label="Клетчатка" unit="г" value={item.fiber_g} />
          <Metric label="ккал" value={item.kcal} />
          <Metric label="Масса" unit="г" value={item.default_grams} />
        </div>
      </section>

      <section className="border-b border-[var(--hairline)] py-6">
        <h3 className="text-[12px] uppercase tracking-[0.06em]">
          дополнительные нутриенты
        </h3>
        {knownNutrients.length ? (
          <div className="mt-4 grid gap-2">
            {knownNutrients.map(({ code, label, value }) => (
              <InfoRow
                key={code}
                label={label}
                value={`${numberLabel(value?.amount)} ${value?.unit ?? ""}`}
              />
            ))}
          </div>
        ) : (
          <p className="mt-4 text-[13px] text-[var(--muted)]">
            дополнительные нутриенты неизвестно
          </p>
        )}
      </section>

      <section className="border-b border-[var(--hairline)] py-6">
        <h3 className="text-[12px] uppercase tracking-[0.06em]">alias</h3>
        {aliases.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {aliases.map((alias) => (
              <Tag key={alias}>{alias}</Tag>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-[13px] text-[var(--muted)]">alias нет</p>
        )}
        <button
          className="mt-4 text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]"
          disabled
          type="button"
        >
          Добавить alias
        </button>
      </section>

      <section className="border-b border-[var(--hairline)] py-6">
        <h3 className="text-[12px] uppercase tracking-[0.06em]">источник</h3>
        <div className="mt-4 grid gap-2">
          <InfoRow
            label="source_name"
            value={item.source_name ?? "неизвестно"}
          />
          <InfoRow label="source_url" value={item.source_url ?? "неизвестно"} />
          <InfoRow label="source_file" value={metadata.source_file ?? "неизвестно"} />
          <InfoRow
            label="source_page"
            value={
              metadata.source_page === null || metadata.source_page === undefined
                ? "неизвестно"
                : String(metadata.source_page)
            }
          />
          <InfoRow
            label="source_confidence"
            value={sourceConfidence}
          />
          <InfoRow label="last_used_at" value={dateLabel(item.last_used_at)} />
        </div>
      </section>

      <section className="border-b border-[var(--hairline)] py-6">
        <h3 className="text-[12px] uppercase tracking-[0.06em]">качество</h3>
        {qualityWarnings.length ? (
          <ul className="mt-4 grid gap-2 pl-5 text-[13px]">
            {qualityWarnings.map((warning) => (
              <li className="list-disc" key={warning}>
                {warning}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-4 text-[13px] text-[var(--muted)]">
            явных предупреждений нет
          </p>
        )}
      </section>

      <div className="sticky bottom-0 mt-auto grid gap-3 border-t border-[var(--hairline)] bg-[var(--bg)] py-4">
        <Button onClick={onUse} variant="primary">
          Использовать в журнале
        </Button>
        <div className="grid grid-cols-2 gap-3">
          <Button disabled>Изменить</Button>
          <Button disabled icon={<Copy size={15} />}>
            Дублировать
          </Button>
          <Button disabled icon={<Archive size={15} />}>
            Архивировать
          </Button>
          <Button disabled icon={<Check size={15} />}>
            Проверено
          </Button>
        </div>
        <Button disabled>Скачать/обновить картинку</Button>
      </div>
    </div>
  );
}

function ImportPanel() {
  return (
    <div className="flex h-full flex-col px-7 py-8">
      <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
        импорт
      </p>
      <h2 className="mt-4 text-[34px] leading-none">Импорт базы</h2>
      <div className="mt-8 grid gap-3 border-y border-[var(--hairline)] py-5">
        <Button disabled>Импорт BK JSON/YAML</Button>
        <Button disabled>Импорт из файла</Button>
        <Button disabled>Вставить JSON/YAML</Button>
      </div>
      <section className="mt-6 border-b border-[var(--hairline)] pb-6">
        <h3 className="text-[12px] uppercase tracking-[0.06em]">preview</h3>
        <div className="mt-4 grid gap-2 text-[13px] text-[var(--muted)]">
          <p>backend import endpoint пока не реализован.</p>
          <p>Импортированные записи должны попадать в статус не проверено.</p>
        </div>
      </section>
    </div>
  );
}

function ManualPanel() {
  return (
    <div className="flex h-full flex-col px-7 py-8">
      <p className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
        вручную
      </p>
      <h2 className="mt-4 text-[34px] leading-none">Добавить вручную</h2>
      <p className="mt-8 border-y border-[var(--hairline)] py-5 text-[13px] text-[var(--muted)]">
        Форма редактирования базы будет подключена отдельным шагом. Сейчас
        используйте backend endpoints продуктов и шаблонов.
      </p>
    </div>
  );
}

function Metric({
  label,
  unit,
  value,
}: {
  label: string;
  unit?: string;
  value?: number | null;
}) {
  const unknown = value === null || value === undefined;
  return (
    <div>
      <div className="font-mono text-[24px] leading-none">
        {unknown ? "неизвестно" : numberLabel(value)}
        {!unknown && unit ? (
          <span className="ml-1 text-[11px] text-[var(--muted)]">{unit}</span>
        ) : null}
      </div>
      <div className="mt-2 text-[11px] uppercase tracking-[0.04em] text-[var(--muted)]">
        {label}
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 border-b border-[var(--hairline)] py-2 text-[13px]">
      <span className="text-[var(--muted)]">{label}</span>
      <span className="break-words text-[var(--fg)]">{value}</span>
    </div>
  );
}

function Tag({ children }: { children: string }) {
  return (
    <span className="border border-[var(--hairline)] px-2 py-1 text-[11px] uppercase tracking-[0.04em] text-[var(--fg)]">
      {children}
    </span>
  );
}

function EmptyDatabaseState({ text }: { text: string }) {
  return (
    <div className="border-y border-[var(--hairline)] py-5 text-[15px] text-[var(--muted)]">
      {text}
    </div>
  );
}
