import { Activity, Camera, Coffee, Cookie, Droplets, ShieldAlert, Syringe } from "lucide-react";
import { useMemo, useState } from "react";
import { FilterChip } from "../../design/primitives/FilterChip";

export type QuickFilter = {
  key: string;
  label: string;
  icon?: typeof Activity;
};

const DEFAULT_CHIPS: QuickFilter[] = [
  { key: "sweet", label: "Сладкое", icon: Cookie },
  { key: "breakfast", label: "Завтраки", icon: Coffee },
  { key: "photoOnly", label: "Только фото", icon: Camera },
  { key: "lowConfidence", label: "Низкая увер.", icon: ShieldAlert },
  { key: "hasCGM", label: "С CGM", icon: Activity },
  { key: "hasInsulin", label: "С инсулином", icon: Syringe },
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
          <FilterChip
            active={isActive}
            icon={Icon ? <Icon size={13} strokeWidth={1.6} /> : null}
            key={chip.key}
            onClick={() => onToggle(chip.key)}
          >
            {chip.label}
          </FilterChip>
        );
      })}
      <FilterChip
        onClick={() => setShowMore((v) => !v)}
      >
        {showMore ? "Меньше" : "Доп. фильтры"}
      </FilterChip>
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
