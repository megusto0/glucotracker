import { useEffect } from "react";
import { useRoutes } from "react-router-dom";
import { useSettingsStore } from "../features/settings/settingsStore";
import { routes } from "./routes";
import Sidebar from "../components/Sidebar";

export function Shell() {
  const element = useRoutes(routes);
  const theme = useSettingsStore((s) => s.theme);

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

  return (
    <div className="gt-app">
      <Sidebar />
      <main className="gt-main">{element}</main>
    </div>
  );
}
