import { useEffect } from "react";
import { Navigate, useLocation, useRoutes } from "react-router-dom";
import { useSettingsStore } from "../features/settings/settingsStore";
import { routes } from "./routes";
import Sidebar from "../components/Sidebar";
import { ConnectionBanner } from "../components/ConnectionBanner";

export function Shell() {
  const element = useRoutes(routes);
  const location = useLocation();
  const theme = useSettingsStore((s) => s.theme);
  const token = useSettingsStore((s) => s.token);
  const currentUser = useSettingsStore((s) => s.currentUser);

  useEffect(() => {
    const root = document.documentElement;
    const apply = (dark: boolean) => root.classList.toggle("dark", dark);
    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      apply(mq.matches);
      const handler = (e: MediaQueryListEvent) => apply(e.matches);
      mq.addEventListener("change", handler);
      return () => mq.removeEventListener("change", handler);
    }
    apply(theme === "dark");
    return () => apply(false);
  }, [theme]);

  const isLoginRoute = location.pathname === "/login";
  const isNightscoutRoute = location.pathname === "/nightscout";

  if (!token.trim() && !isLoginRoute) {
    return (
      <Navigate
        replace
        state={{ from: `${location.pathname}${location.search}` }}
        to="/login"
      />
    );
  }

  if (token.trim() && isLoginRoute) {
    return <Navigate replace to="/" />;
  }

  if (
    isNightscoutRoute &&
    currentUser &&
    !currentUser.features.includes("glucose")
  ) {
    return <Navigate replace to="/" />;
  }

  if (isNightscoutRoute) {
    return (
      <div className="nightscout-app">
        <main className="nightscout-main">{element}</main>
      </div>
    );
  }

  return isLoginRoute ? (
    <div className="gt-app">
      <main className="gt-main">{element}</main>
    </div>
  ) : (
    <div className="gt-app">
      <Sidebar />
      <main className="gt-main">{element}</main>
      <ConnectionBanner />
    </div>
  );
}
