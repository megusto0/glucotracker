import type { ButtonHTMLAttributes, ReactNode } from "react";

type FilterChipProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean;
  icon?: ReactNode;
};

export function FilterChip({
  active = false,
  children,
  className = "",
  icon,
  ...props
}: FilterChipProps) {
  const activeClass = active
    ? "border-[var(--hairline-2)] bg-[var(--surface-2)] text-[var(--ink)] shadow-[inset_0_-2px_0_var(--ink-3)]"
    : "border-[var(--hairline)] bg-transparent text-[var(--ink-3)] hover:border-[var(--hairline-2)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)]";

  return (
    <button
      className={`inline-flex h-[28px] items-center justify-center gap-1.5 rounded-[var(--radius)] border px-3 text-[12px] font-normal uppercase leading-none tracking-[0.04em] transition ${activeClass} ${className}`}
      type="button"
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}
