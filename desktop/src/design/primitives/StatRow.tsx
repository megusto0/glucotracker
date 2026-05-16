import type { ReactNode } from "react";

export function StatRow({ label, value }: { label: ReactNode; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-baseline gap-4 border-b border-[var(--hairline)] py-2 text-[13px]">
      <span className="min-w-0 text-[var(--ink-3)]">{label}</span>
      <span className="text-right font-mono text-[var(--ink)]">{value}</span>
    </div>
  );
}
