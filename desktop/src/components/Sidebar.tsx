import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  Activity, BarChart3, BookOpen, Clock, Database, LogOut, Settings,
} from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useApiConfig,
  useSettingsStore,
} from "../features/settings/settingsStore";
import { apiClient } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import { formatMmol } from "../utils/nutritionFormat";

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

const pad = (value: number) => value.toString().padStart(2, "0");

const toDateTimeInput = (date: Date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;

const formatGlucoseAge = (timestamp?: string | null) => {
  if (!timestamp) return "—";
  const pointMs = Date.parse(timestamp);
  if (!Number.isFinite(pointMs)) return "—";
  const elapsedMs = Math.max(0, Date.now() - pointMs);
  if (elapsedMs < 60_000) return "сейчас";
  const minutes = Math.round(elapsedMs / 60_000);
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
  }).format(new Date(timestamp));
};

const nightscoutTrendSymbol = (trend?: string | null) => {
  const normalized = trend?.toLowerCase().replace(/[\s_-]+/g, "");
  switch (normalized) {
    case "doubleup":
      return "↑↑";
    case "singleup":
      return "↑";
    case "fortyfiveup":
      return "↗";
    case "flat":
      return "→";
    case "fortyfivedown":
      return "↘";
    case "singledown":
      return "↓";
    case "doubledown":
      return "↓↓";
    default:
      return null;
  }
};

export default function Sidebar() {
  const config = useApiConfig();
  const clearAuthSession = useSettingsStore((s) => s.clearAuthSession);
  const currentUser = useSettingsStore((s) => s.currentUser);
  const refreshToken = useSettingsStore((s) => s.refreshToken);
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const isGlucosePage = location.pathname === "/glucose";

  const logout = () => {
    const tokenToRevoke = refreshToken.trim();
    if (tokenToRevoke) {
      void apiClient.logout(config, { refresh_token: tokenToRevoke });
    }
    clearAuthSession();
    queryClient.clear();
    navigate("/login", { replace: true });
  };

  const { data: latestReading } = useQuery({
    queryKey: queryKeys.nightscoutLatestReading,
    queryFn: () => apiClient.getNightscoutLatestReading(config),
    enabled: !!config.baseUrl && !!config.token,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const { data: sparkline } = useQuery({
    queryKey: ["sidebar-glucose-sparkline", config.baseUrl],
    queryFn: () => {
      const to = new Date();
      const from = new Date(to.getTime() - 2 * 60 * 60 * 1000);
      return apiClient.getGlucoseDashboard(
        config,
        toDateTimeInput(from),
        toDateTimeInput(to),
        "raw",
      );
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
        timestamp: last.timestamp,
        trend: delta,
        recent: recent.filter((v): v is number => typeof v === "number"),
      };
    },
  });

  const latestValue = latestReading?.value_mmol_l ?? sparkline?.value ?? null;
  const latestTimestamp = latestReading?.timestamp ?? sparkline?.timestamp ?? null;
  const latestTrend = nightscoutTrendSymbol(latestReading?.trend);
  const trendChar =
    latestTrend ??
    ((sparkline?.trend ?? 0) > 0.2 ? "↑" : (sparkline?.trend ?? 0) < -0.2 ? "↓" : "→");
  const trendColor =
    trendChar.includes("↑") || trendChar === "↗"
      ? "var(--accent)"
      : trendChar.includes("↓") || trendChar === "↘"
        ? "var(--warn)"
        : "var(--ink-3)";
  const trendDelta = latestTrend
    ? ""
    : sparkline?.trend
      ? `${sparkline.trend > 0 ? "+" : ""}${formatMmol(sparkline.trend)}`
      : "";

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

      {!isGlucosePage && latestValue != null && (
        <div className="gt-side-glucose" onClick={() => navigate("/glucose")} title="Перейти к графику глюкозы">
          <div className="row" style={{ alignItems: "baseline", justifyContent: "space-between" }}>
            <span className="lbl">сейчас</span>
            <span className="mono" style={{ fontSize: 9, color: "var(--ink-4)" }}>{formatGlucoseAge(latestTimestamp)}</span>
          </div>
          <div className="row" style={{ alignItems: "baseline", gap: 4, marginTop: 4 }}>
            <span className="mono" style={{ fontSize: 22, fontWeight: 500, letterSpacing: "-0.01em" }}>
              {formatMmol(latestValue)}
            </span>
            <span style={{ fontSize: 10, color: "var(--ink-3)" }}>ммоль/л</span>
            <span className="spacer" />
            <span style={{ display: "inline-flex", alignItems: "center", gap: 2, fontSize: 10, color: trendColor, fontFamily: "var(--mono)" }}>
              {trendChar} {trendDelta}
            </span>
          </div>
          {sparkline?.recent.length && sparkline.recent.length > 1 ? (
            <div style={{ marginTop: 6 }}>
              <MiniSparkline points={sparkline.recent} />
            </div>
          ) : null}
          <div className="mono" style={{ fontSize: 9, color: "var(--ink-4)", marginTop: 4, textAlign: "right" }}>
            последние 60 мин
          </div>
        </div>
      )}
      {isGlucosePage && (
        <div
          aria-hidden="true"
          style={{ marginTop: "auto", marginBottom: 6, minHeight: 112 }}
        />
      )}
      <div className="gt-side-foot">
        <div className="gt-avatar">
          {(currentUser?.username ?? "?").slice(0, 1).toUpperCase()}
        </div>
        <div className="col" style={{ lineHeight: 1.3 }}>
          <span style={{ color: "var(--ink)", fontWeight: 500 }}>
            {currentUser?.username ?? "glucotracker"}
          </span>
          <span className="gt-side-status">
            {config.baseUrl ? "подключён" : "не подключён"}
          </span>
        </div>
        <button
          aria-label="Выйти"
          className="btn"
          onClick={logout}
          style={{ height: 28, marginLeft: "auto", minHeight: 28, padding: 6 }}
          title="Выйти"
          type="button"
        >
          <LogOut size={13} />
        </button>
      </div>
    </aside>
  );
}
