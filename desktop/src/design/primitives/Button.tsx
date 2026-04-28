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
    primary: "border-[var(--fg)] bg-[var(--fg)] text-[var(--surface)]",
    quiet: "border-[var(--hairline)] bg-[var(--surface)] text-[var(--fg)]",
    danger: "border-[var(--danger)] bg-[var(--surface)] text-[var(--danger)]",
  };

  return (
    <button
      className={`inline-flex h-10 items-center justify-center gap-2 border px-3 text-[13px] font-medium uppercase tracking-[0.06em] transition duration-200 ease-out hover:border-[var(--fg)] disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      type="button"
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}
