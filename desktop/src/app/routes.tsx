import { lazy, Suspense } from "react";
import type { RouteObject } from "react-router-dom";
import { LoginPage } from "../features/auth/LoginPage";
import { ChatPage } from "../features/chat/ChatPage";
import { DatabasePage } from "../features/database/DatabasePage";
import { FeedPage } from "../features/feed/FeedPage";
import { GlucosePage } from "../features/glucose/GlucosePage";
import { InsulinLinksPage } from "../features/insulinLinks/InsulinLinksPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { StatsPage } from "../features/stats/StatsPage";
import { TwinPage } from "../features/twin/TwinPage";

const NightscoutPage = lazy(() =>
  import("../features/nightscoutView/NightscoutPage").then((module) => ({
    default: module.NightscoutPage,
  })),
);

export const routes: RouteObject[] = [
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/",
    element: <ChatPage />,
  },
  {
    path: "/feed",
    element: <FeedPage />,
  },
  {
    path: "/stats",
    element: <StatsPage />,
  },
  {
    path: "/glucose",
    element: <GlucosePage />,
  },
  {
    path: "/nightscout",
    element: (
      <Suspense fallback={<div className="nightscout-route-loading">Загружаю Nightscout…</div>}>
        <NightscoutPage />
      </Suspense>
    ),
  },
  {
    path: "/twin",
    element: <TwinPage />,
  },
  {
    path: "/insulin-links",
    element: <InsulinLinksPage />,
  },
  {
    path: "/database",
    element: <DatabasePage />,
  },
  {
    path: "/settings",
    element: <SettingsPage />,
  },
];
