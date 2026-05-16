import type { HTMLAttributes, ReactNode } from "react";

type SectionLabelProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
};

export function SectionLabel({ children, className = "", ...props }: SectionLabelProps) {
  return (
    <div
      className={`text-[10px] font-medium uppercase leading-none tracking-[0.14em] text-[var(--ink-4)] ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
