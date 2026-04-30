import { create } from "zustand";
import { persist } from "zustand/middleware";
import { useShallow } from "zustand/react/shallow";
import type { ApiConfig } from "../../api/client";

export const defaultBackendUrl = "http://127.0.0.1:8000";

export type Theme = "light" | "dark" | "system";

type SettingsState = ApiConfig & {
  theme: Theme;
  clearUiSettings: () => void;
  setBackendUrl: (backendUrl: string) => void;
  setTheme: (theme: Theme) => void;
  setToken: (token: string) => void;
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      baseUrl: defaultBackendUrl,
      theme: "system",
      token: "",
      clearUiSettings: () => set({ baseUrl: defaultBackendUrl, token: "" }),
      setBackendUrl: (baseUrl) => set({ baseUrl }),
      setTheme: (theme) => set({ theme }),
      setToken: (token) => set({ token }),
    }),
    {
      name: "glucotracker.settings",
      partialize: ({ baseUrl, theme, token }) => ({ baseUrl, theme, token }),
    },
  ),
);

export const selectApiConfig = (state: SettingsState): ApiConfig => ({
  baseUrl: state.baseUrl,
  token: state.token,
});

export function useApiConfig() {
  return useSettingsStore(useShallow(selectApiConfig));
}
