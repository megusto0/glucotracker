import type { HTMLAttributes, ReactNode } from "react";

type ProgressTone = "neutral" | "accent" | "good" | "ink";

const progressColor: Record<ProgressTone, string> = {
  accent: "var(--accent)",
  good: "var(--good)",
  ink: "var(--ink)",
  neutral: "var(--ink-3)",
};

type KpiCardProps = HTMLAttributes<HTMLDivElement> & {
  label: ReactNode;
  progress?: number | null;
  progressTone?: ProgressTone;
  sub?: ReactNode;
  unit?: ReactNode;
  value: ReactNode;
  valueSize?: number;
};

export function KpiCard({
  className = "",
  label,
  progress,
  progressTone = "neutral",
  sub,
  unit,
  value,
  valueSize = 30,
  ...props
}: KpiCardProps) {
  const width =
    progress === null || progress === undefined
      ? null
      : `${Math.min(100, Math.max(0, progress * 100))}%`;

  return (
    <div className={`gt-kpi-card ${className}`} {...props}>
      <div className="gt-kpi-label">{label}</div>
      <div className="gt-kpi-value" style={{ fontSize: valueSize }}>
        {value}
        {unit ? <span className="gt-kpi-unit">{unit}</span> : null}
      </div>
      {width ? (
        <div className="gt-kpi-progress" aria-hidden="true">
          <i style={{ background: progressColor[progressTone], width }} />
        </div>
      ) : null}
      {sub ? <div className="gt-kpi-sub">{sub}</div> : null}
    </div>
  );
}
