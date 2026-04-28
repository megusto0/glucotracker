import { create } from "zustand";
import { persist } from "zustand/middleware";
import { useShallow } from "zustand/react/shallow";
import type { ApiConfig } from "../../api/client";

export const defaultBackendUrl = "http://127.0.0.1:8000";

type SettingsState = ApiConfig & {
  clearUiSettings: () => void;
  setBackendUrl: (backendUrl: string) => void;
  setToken: (token: string) => void;
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      baseUrl: defaultBackendUrl,
      token: "",
      clearUiSettings: () => set({ baseUrl: defaultBackendUrl, token: "" }),
      setBackendUrl: (baseUrl) => set({ baseUrl }),
      setToken: (token) => set({ token }),
    }),
    {
      name: "glucotracker.settings",
      partialize: ({ baseUrl, token }) => ({ baseUrl, token }),
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
