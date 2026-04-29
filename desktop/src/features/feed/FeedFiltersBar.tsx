import type { FeedFilters } from "./feedService";

export function FeedFiltersBar({
  filters,
  onChange,
}: {
  filters: FeedFilters;
  onChange: (next: FeedFilters) => void;
}) {
  return (
    <section className="mt-8 grid grid-cols-[minmax(260px,1fr)_140px_140px_140px] gap-3 border-y border-[var(--hairline)] py-4">
      <label className="grid gap-2">
        <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          поиск
        </span>
        <input
          aria-label="Поиск по еде"
          className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent px-0 text-[20px] outline-none focus:border-[var(--fg)]"
          onChange={(event) =>
            onChange({ ...filters, q: event.target.value })
          }
          placeholder="еда, заметка, позиция"
          value={filters.q}
        />
      </label>
      <label className="grid gap-2">
        <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          от
        </span>
        <input
          aria-label="Дата от"
          className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent px-0 font-mono text-[14px] outline-none focus:border-[var(--fg)]"
          onChange={(event) =>
            onChange({ ...filters, from: event.target.value })
          }
          type="date"
          value={filters.from}
        />
      </label>
      <label className="grid gap-2">
        <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          до
        </span>
        <input
          aria-label="Дата до"
          className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent px-0 font-mono text-[14px] outline-none focus:border-[var(--fg)]"
          onChange={(event) =>
            onChange({ ...filters, to: event.target.value })
          }
          type="date"
          value={filters.to}
        />
      </label>
      <label className="grid gap-2">
        <span className="text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
          статус
        </span>
        <select
          aria-label="Фильтр статуса"
          className="h-11 border-0 border-b border-[var(--hairline)] bg-transparent px-0 text-[14px] uppercase tracking-[0.06em] outline-none focus:border-[var(--fg)]"
          onChange={(event) =>
            onChange({
              ...filters,
              status: event.target.value as FeedFilters["status"],
            })
          }
          value={filters.status}
        >
          <option value="active">активные</option>
          <option value="accepted">принятые</option>
          <option value="draft">черновики</option>
          <option value="discarded">отмененные</option>
        </select>
      </label>
    </section>
  );
}
