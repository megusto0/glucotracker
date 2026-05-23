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
