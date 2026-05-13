import type { HTMLAttributes, ReactNode } from "react";

type TagProps = HTMLAttributes<HTMLSpanElement> & {
  children: ReactNode;
};

export function Tag({ children, className = "", ...props }: TagProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-[2px] bg-[var(--surface-2)] px-[6px] py-[2px] text-[10px] font-medium uppercase leading-none tracking-[0.06em] text-[var(--ink-3)] ${className}`}
      {...props}
    >
      {children}
    </span>
  );
}
