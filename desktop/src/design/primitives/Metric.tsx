type MetricProps = {
  label: string;
  value: number | string;
  unit?: string;
};

export function Metric({ label, value, unit }: MetricProps) {
  return (
    <section className="border-y border-[var(--hairline)] bg-transparent py-4">
      <div className="text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
        {label}
      </div>
      <div className="mt-5 flex items-baseline gap-2 font-mono text-[40px] leading-none text-[var(--fg)]">
        <span>{value}</span>
        {unit ? (
          <span className="text-[12px] uppercase tracking-[0.06em] text-[var(--muted)]">
            {unit}
          </span>
        ) : null}
      </div>
    </section>
  );
}
