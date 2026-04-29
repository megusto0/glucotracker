import { Activity, Droplets, ShieldAlert, Syringe } from "lucide-react";
import { useMemo, useState } from "react";

export type QuickFilter = {
  key: string;
  label: string;
  icon?: typeof Activity;
};

const DEFAULT_CHIPS: QuickFilter[] = [
  { key: "hasCGM", label: "С CGM", icon: Activity },
  { key: "hasInsulin", label: "С инсулином", icon: Syringe },
  { key: "lowConfidence", label: "Низкая уверенность", icon: ShieldAlert },
];

export function QuickFilterChips({
  active,
  onToggle,
}: {
  active: Set<string>;
  onToggle: (key: string) => void;
}) {
  const [showMore, setShowMore] = useState(false);
  const chips = showMore
    ? [...DEFAULT_CHIPS, { key: "hasNS", label: "NS-события", icon: Droplets }]
    : DEFAULT_CHIPS;

  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      {chips.map((chip) => {
        const Icon = chip.icon;
        const isActive = active.has(chip.key);
        return (
          <button
            className={`flex items-center gap-1.5 border px-3 py-1.5 text-[12px] uppercase tracking-[0.04em] transition ${
              isActive
                ? "border-[var(--fg)] bg-[var(--fg)] text-[var(--surface)]"
                : "border-[var(--hairline)] text-[var(--muted)] hover:border-[var(--fg)] hover:text-[var(--fg)]"
            }`}
            key={chip.key}
            onClick={() => onToggle(chip.key)}
            type="button"
          >
            {Icon ? <Icon size={13} strokeWidth={1.6} /> : null}
            {chip.label}
          </button>
        );
      })}
      <button
        className="border border-[var(--hairline)] px-3 py-1.5 text-[12px] uppercase tracking-[0.04em] text-[var(--muted)] transition hover:text-[var(--fg)]"
        onClick={() => setShowMore((v) => !v)}
        type="button"
      >
        {showMore ? "Меньше" : "Доп. фильтры"}
      </button>
    </div>
  );
}

export function useQuickFilterChips() {
  const [active, setActive] = useState<Set<string>>(new Set());

  const toggle = useMemo(
    () => (key: string) =>
      setActive((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
        }
        return next;
      }),
    [],
  );

  return { active, toggle };
}
