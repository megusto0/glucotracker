import { KeyRound, LogIn, Wifi } from "lucide-react";
import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { apiClient, apiErrorMessage } from "../../api/client";
import {
  defaultBackendUrl,
  useSettingsStore,
} from "../settings/settingsStore";

type LoginLocationState = {
  from?: string;
};

export function LoginPage() {
  const baseUrl = useSettingsStore((s) => s.baseUrl);
  const setAuthSession = useSettingsStore((s) => s.setAuthSession);
  const setBackendUrl = useSettingsStore((s) => s.setBackendUrl);
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("admin");
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as LoginLocationState | null;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsPending(true);

    const config = { baseUrl: baseUrl || defaultBackendUrl, token: "" };
    try {
      const tokens = await apiClient.login(config, {
        username: username.trim(),
        password,
      });
      const user = await apiClient.me({ ...config, token: tokens.access });
      setAuthSession(tokens, user);
      navigate(state?.from || "/", { replace: true });
    } catch (loginError) {
      setError(apiErrorMessage(loginError, "Не удалось войти."));
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div
      className="gt-page"
      style={{
        alignItems: "center",
        display: "flex",
        justifyContent: "center",
        minHeight: "100%",
        padding: 32,
      }}
    >
      <form
        className="card card-pad"
        onSubmit={(event) => void submit(event)}
        style={{ maxWidth: 420, width: "100%" }}
      >
        <div className="gt-brand" style={{ padding: 0 }}>
          <span className="gt-dot" />
          <b>gluco</b>tracker
        </div>
        <div className="lbl" style={{ marginTop: 22 }}>
          вход
        </div>
        <h1 className="gt-h1" style={{ fontSize: 28, marginBottom: 18 }}>
          Подключение к дневнику
        </h1>

        <div className="field" style={{ marginBottom: 12 }}>
          <label>
            <Wifi size={13} /> backend
          </label>
          <input
            autoComplete="url"
            onChange={(event) => setBackendUrl(event.target.value)}
            placeholder={defaultBackendUrl}
            value={baseUrl}
          />
        </div>

        <div className="field" style={{ marginBottom: 12 }}>
          <label>пользователь</label>
          <input
            autoComplete="username"
            onChange={(event) => setUsername(event.target.value)}
            value={username}
          />
        </div>

        <div className="field" style={{ marginBottom: 18 }}>
          <label>
            <KeyRound size={13} /> пароль
          </label>
          <input
            autoComplete="current-password"
            autoFocus
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            value={password}
          />
        </div>

        {error ? (
          <div
            className="card"
            style={{
              borderColor: "var(--warn-soft)",
              color: "var(--warn)",
              fontSize: 12,
              marginBottom: 14,
            }}
          >
            {error}
          </div>
        ) : null}

        <button
          className="btn dark"
          disabled={isPending || !username.trim() || !password}
          style={{ justifyContent: "center", width: "100%" }}
          type="submit"
        >
          <LogIn size={14} />
          {isPending ? "Вхожу..." : "Войти"}
        </button>
      </form>
    </div>
  );
}
