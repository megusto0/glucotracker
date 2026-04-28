import {
  BarChart3,
  CircleDot,
  Database,
  List,
  Settings,
  SquarePen,
} from "lucide-react";
import { NavLink, useRoutes } from "react-router-dom";
import { routes } from "./routes";

const navItems = [
  { to: "/", label: "Журнал", icon: SquarePen },
  { to: "/feed", label: "История", icon: List },
  { to: "/stats", label: "Статистика", icon: BarChart3 },
  { to: "/database", label: "База", icon: Database },
  { to: "/settings", label: "Настройки", icon: Settings },
];

export function Shell() {
  const element = useRoutes(routes);

  return (
    <div className="h-screen overflow-hidden bg-[var(--bg)] text-[var(--fg)]">
      <aside className="fixed inset-y-0 left-0 z-10 flex w-[192px] flex-col border-r border-[var(--hairline)] bg-[var(--bg)]">
        <div className="flex h-[88px] items-center px-7 text-[18px]">
          glucotracker
        </div>
        <nav className="flex w-full flex-1 flex-col gap-2 px-0 py-5">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              aria-label={label}
              className={({ isActive }) =>
                `relative mx-3 flex h-12 items-center gap-4 px-4 text-[14px] text-[var(--muted)] transition duration-200 ease-out hover:text-[var(--fg)] ${
                  isActive
                    ? "border-l-2 border-[var(--fg)] bg-[rgba(255,255,255,0.38)] text-[var(--fg)]"
                    : "border-l-2 border-transparent"
                }`
              }
              end={to === "/"}
              key={to}
              title={label}
              to={to}
            >
              <Icon size={20} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="grid gap-2 px-7 py-6">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center bg-[var(--fg)] font-mono text-[12px] text-[var(--surface)]">
              g1
            </span>
            <span className="grid gap-0.5">
              <span className="text-[12px] text-[var(--fg)]">glucotracker</span>
              <span className="text-[11px] text-[var(--muted)]">личное</span>
            </span>
          </div>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.06em] text-[var(--muted)]">
            <CircleDot size={12} />
            локальный дневник
          </div>
        </div>
      </aside>
      <main className="ml-[192px] h-screen overflow-hidden">{element}</main>
    </div>
  );
}
