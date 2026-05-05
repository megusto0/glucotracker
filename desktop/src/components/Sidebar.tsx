import { NavLink, useNavigate } from "react-router-dom";
import {
  BookOpen, Clock, Activity, BarChart3, Database, Settings,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useApiConfig } from "../features/settings/settingsStore";
import { apiClient } from "../api/client";

const NAV = [
  { to: "/", label: "Журнал", icon: BookOpen },
  { to: "/feed", label: "История", icon: Clock },
  { to: "/glucose", label: "Глюкоза", icon: Activity },
  { to: "/stats", label: "Статистика", icon: BarChart3 },
  { to: "/database", label: "База продуктов", icon: Database },
  { to: "/settings", label: "Настройки", icon: Settings },
];

function MiniSparkline({ points }: { points: number[] }) {
  const w = 80, h = 22;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const path = points.map((y, i) => {
    const x = (i / (points.length - 1)) * w;
    const yy = h - ((y - min) / range) * h;
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${yy.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      <path d={path} fill="none" stroke="var(--ink)" strokeWidth="1.2" />
      <circle cx={w} cy={h - ((points[points.length - 1] - min) / range) * h} r="2" fill="var(--accent)" />
    </svg>
  );
}

export default function Sidebar() {
  const config = useApiConfig();
  const navigate = useNavigate();

  const { data: glucose } = useQuery({
    queryKey: ["sidebar-glucose"],
    queryFn: () => {
      const to = new Date();
      const from = new Date(to.getTime() - 2 * 60 * 60 * 1000);
      const pad = (n: number) => n.toString().padStart(2, "0");
      const fmt = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
      return apiClient.getGlucoseDashboard(config, fmt(from), fmt(to), "raw");
    },
    enabled: !!config.baseUrl && !!config.token,
    refetchInterval: 60_000 * 5,
    staleTime: 60_000 * 2,
    select: (d) => {
      const pts = d.points ?? [];
      if (!pts.length) return null;
      const last = pts[pts.length - 1];
      const recent = pts.slice(-12).map(p => p.display_value ?? p.raw_value);
      const prev = pts.length > 1 ? pts[pts.length - 2] : null;
      const delta = prev ? (last.display_value ?? last.raw_value) - (prev.display_value ?? prev.raw_value) : 0;
      return {
        value: last.display_value ?? last.raw_value,
        trend: delta,
        recent: recent.filter((v): v is number => typeof v === "number"),
      };
    },
  });

  const trendChar = (glucose?.trend ?? 0) > 0.2 ? "↑" : (glucose?.trend ?? 0) < -0.2 ? "↓" : "→";
  const trendColor = (glucose?.trend ?? 0) > 0.2 ? "var(--accent)" : (glucose?.trend ?? 0) < -0.2 ? "var(--warn)" : "var(--ink-3)";

  return (
    <aside className="gt-sidebar">
      <div className="gt-brand">
        <span className="gt-dot" />
        <b>gluco</b>tracker
      </div>

      <nav className="gt-nav">
        <div className="gt-nav-section">Основное</div>
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            className={({ isActive }) => isActive ? "active" : ""}
          >
            <n.icon />
            {n.label}
          </NavLink>
        ))}
      </nav>

      {glucose?.value != null && (
        <div className="gt-side-glucose" onClick={() => navigate("/glucose")} title="Перейти к графику глюкозы">
          <div className="row" style={{ alignItems: "baseline", justifyContent: "space-between" }}>
            <span className="lbl">сейчас</span>
            <span className="mono" style={{ fontSize: 9, color: "var(--ink-4)" }}>2 мин назад</span>
          </div>
          <div className="row" style={{ alignItems: "baseline", gap: 4, marginTop: 4 }}>
            <span className="mono" style={{ fontSize: 22, fontWeight: 500, letterSpacing: "-0.01em" }}>
              {glucose.value.toFixed(1).replace(".", ",")}
            </span>
            <span style={{ fontSize: 10, color: "var(--ink-3)" }}>ммоль/л</span>
            <span className="spacer" />
            <span style={{ display: "inline-flex", alignItems: "center", gap: 2, fontSize: 10, color: trendColor, fontFamily: "var(--mono)" }}>
              {trendChar} {glucose.trend !== 0 ? `${glucose.trend > 0 ? "+" : ""}${glucose.trend.toFixed(1).replace(".", ",")}` : ""}
            </span>
          </div>
          {glucose.recent.length > 1 && (
            <div style={{ marginTop: 6 }}>
              <MiniSparkline points={glucose.recent} />
            </div>
          )}
          <div className="mono" style={{ fontSize: 9, color: "var(--ink-4)", marginTop: 4, textAlign: "right" }}>
            последние 60 мин
          </div>
        </div>
      )}

      <div className="gt-side-foot">
        <div className="gt-avatar">
          ?
        </div>
        <div className="col" style={{ lineHeight: 1.3 }}>
          <span style={{ color: "var(--ink)", fontWeight: 500 }}>glucotracker</span>
          <span className="gt-side-status">
            {config.baseUrl ? "подключён" : "не подключён"}
          </span>
        </div>
      </div>
    </aside>
  );
}
