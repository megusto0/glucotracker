import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: ReactNode;
  variant?: "primary" | "quiet" | "danger";
};

export function Button({
  children,
  icon,
  variant = "quiet",
  className = "",
  ...props
}: ButtonProps) {
  const variants = {
    primary: "border-[var(--ink-3)] bg-[var(--surface)] text-[var(--ink)] hover:border-[var(--ink-2)] hover:bg-[var(--surface-2)]",
    quiet: "border-[var(--hairline-2)] bg-[var(--surface)] text-[var(--ink-2)] hover:border-[var(--ink-3)] hover:bg-[var(--surface-2)]",
    danger: "border-[var(--warn-soft)] bg-[var(--surface)] text-[var(--warn)] hover:border-[var(--warn)]",
  };

  return (
    <button
      className={`inline-flex h-[30px] items-center justify-center gap-1.5 rounded-[var(--radius)] border px-3 text-[12px] font-normal leading-none transition duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      type="button"
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}
