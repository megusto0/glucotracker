import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Component, type ErrorInfo, type ReactNode, useEffect, useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { connectionManager } from "../api/connectionManager";
import {
  ApiError,
  apiClient,
  setAuthSessionManager,
  setConnectionNotifier,
} from "../api/client";
import { selectApiConfig, useSettingsStore } from "../features/settings/settingsStore";
import { Shell } from "./Shell";
import "../App.css";

function isTransientError(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403 || error.status === 404) {
      return false;
    }
  }
  return failureCount < 3;
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => isTransientError(failureCount, error),
        retryDelay: (attemptIndex) => {
          const delay = Math.min(1_000 * Math.pow(2, attemptIndex), 30_000);
          const jitter = Math.random() * 1_000;
          return delay + jitter;
        },
        staleTime: 30_000,
        refetchOnReconnect: true,
        refetchOnWindowFocus: true,
        networkMode: "offlineFirst",
      },
      mutations: {
        retry: (failureCount, error) => isTransientError(failureCount, error),
        retryDelay: (attemptIndex) =>
          Math.min(1_000 * Math.pow(2, attemptIndex), 10_000),
        networkMode: "offlineFirst",
      },
    },
  });
}

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class AppErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[AppErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            height: "100vh",
            gap: 16,
            padding: 32,
            textAlign: "center",
            fontFamily: "var(--sans)",
            color: "var(--ink)",
          }}
        >
          <h2 style={{ fontFamily: "var(--serif)", fontWeight: 500, margin: 0 }}>
            Что-то пошло не так
          </h2>
          <p
            style={{
              fontSize: 13,
              color: "var(--ink-3)",
              maxWidth: 420,
              lineHeight: 1.5,
            }}
          >
            Произошла непредвиденная ошибка. Попробуйте перезагрузить страницу.
          </p>
          <pre
            style={{
              fontSize: 11,
              color: "var(--warn)",
              maxWidth: 600,
              overflow: "auto",
              textAlign: "left",
              padding: 12,
              background: "var(--surface-2)",
              borderRadius: 4,
            }}
          >
            {this.state.error?.message ?? "Unknown error"}
          </pre>
          <button
            className="btn dark"
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.reload();
            }}
          >
            Перезагрузить
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function App() {
  const [queryClient] = useState(createQueryClient);

  useEffect(() => {
    let refreshAccessTokenPromise: Promise<string | null> | null = null;

    const refreshAccessTokenOnce = async () => {
      const settings = useSettingsStore.getState();
      const refreshToken = settings.refreshToken.trim();
      const currentUser = settings.currentUser;
      if (!refreshToken || !currentUser) {
        return null;
      }

      try {
        const tokens = await apiClient.refreshAuthToken(
          { baseUrl: settings.baseUrl, token: "" },
          { refresh_token: refreshToken },
        );
        useSettingsStore.getState().setAuthSession(tokens, currentUser);
        return tokens.access;
      } catch {
        const latest = useSettingsStore.getState();
        if (
          latest.refreshToken.trim() &&
          latest.refreshToken.trim() !== refreshToken &&
          latest.token.trim()
        ) {
          return latest.token.trim();
        }
        return null;
      }
    };

    connectionManager.init(() => selectApiConfig(useSettingsStore.getState()));

    setConnectionNotifier({
      onSuccess: () => connectionManager.notifyRequestSucceeded(),
      onFailure: (error: string) => connectionManager.notifyRequestFailed(error),
    });

    setAuthSessionManager({
      refreshAccessToken: async () => {
        if (!refreshAccessTokenPromise) {
          refreshAccessTokenPromise = refreshAccessTokenOnce().finally(() => {
            refreshAccessTokenPromise = null;
          });
        }
        return refreshAccessTokenPromise;
      },
    });

    const unsubscribe = connectionManager.subscribe((status) => {
      if (status === "connected") {
        queryClient.invalidateQueries().catch(() => {});
      }
    });

    return () => {
      unsubscribe();
      connectionManager.destroy();
      setAuthSessionManager(null);
      setConnectionNotifier(null);
    };
  }, [queryClient]);

  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename={import.meta.env.BASE_URL}>
          <Shell />
        </BrowserRouter>
      </QueryClientProvider>
    </AppErrorBoundary>
  );
}
