import type { ReactNode } from "react";

type StatusTextProps = {
  tone?: "muted" | "ok" | "danger";
  children: ReactNode;
};

export function StatusText({ tone = "muted", children }: StatusTextProps) {
  const tones = {
    muted: "text-[var(--muted)]",
    ok: "text-[var(--ok)]",
    danger: "text-[var(--danger)]",
  };

  return (
    <span className={`text-[12px] uppercase tracking-[0.06em] ${tones[tone]}`}>
      {children}
    </span>
  );
}
