import { create } from "zustand";
import { persist } from "zustand/middleware";
import { useShallow } from "zustand/react/shallow";
import type {
  ApiConfig,
  CurrentUserDetailResponse,
  IssuedTokensResponse,
} from "../../api/client";

export const defaultBackendUrl = "http://127.0.0.1:8000";

export type Theme = "light" | "dark" | "system";

type SettingsState = ApiConfig & {
  accessExpiresAt: string | null;
  currentUser: CurrentUserDetailResponse | null;
  refreshExpiresAt: string | null;
  refreshToken: string;
  theme: Theme;
  clearAuthSession: () => void;
  clearUiSettings: () => void;
  setAuthSession: (
    tokens: IssuedTokensResponse,
    user: CurrentUserDetailResponse,
  ) => void;
  setBackendUrl: (backendUrl: string) => void;
  setTheme: (theme: Theme) => void;
  setToken: (token: string) => void;
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      accessExpiresAt: null,
      baseUrl: defaultBackendUrl,
      currentUser: null,
      refreshExpiresAt: null,
      refreshToken: "",
      theme: "system",
      token: "",
      clearAuthSession: () =>
        set({
          accessExpiresAt: null,
          currentUser: null,
          refreshExpiresAt: null,
          refreshToken: "",
          token: "",
        }),
      clearUiSettings: () =>
        set({
          accessExpiresAt: null,
          baseUrl: defaultBackendUrl,
          currentUser: null,
          refreshExpiresAt: null,
          refreshToken: "",
          token: "",
        }),
      setAuthSession: (tokens, user) =>
        set({
          accessExpiresAt: tokens.access_expires_at,
          currentUser: user,
          refreshExpiresAt: tokens.refresh_expires_at,
          refreshToken: tokens.refresh,
          token: tokens.access,
        }),
      setBackendUrl: (baseUrl) => set({ baseUrl }),
      setTheme: (theme) => set({ theme }),
      setToken: (token) =>
        set({
          accessExpiresAt: null,
          currentUser: null,
          refreshExpiresAt: null,
          refreshToken: "",
          token,
        }),
    }),
    {
      name: "glucotracker.settings",
      partialize: ({
        accessExpiresAt,
        baseUrl,
        currentUser,
        refreshExpiresAt,
        refreshToken,
        theme,
        token,
      }) => ({
        accessExpiresAt,
        baseUrl,
        currentUser,
        refreshExpiresAt,
        refreshToken,
        theme,
        token,
      }),
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
