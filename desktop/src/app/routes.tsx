import type { RouteObject } from "react-router-dom";
import { ChatPage } from "../features/chat/ChatPage";
import { DatabasePage } from "../features/database/DatabasePage";
import { FeedPage } from "../features/feed/FeedPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { StatsPage } from "../features/stats/StatsPage";

export const routes: RouteObject[] = [
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
    path: "/database",
    element: <DatabasePage />,
  },
  {
    path: "/settings",
    element: <SettingsPage />,
  },
];
