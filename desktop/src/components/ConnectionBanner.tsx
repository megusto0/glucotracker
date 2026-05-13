import { useEffect, useState } from "react";
import { connectionManager } from "../api/connectionManager";

export function ConnectionBanner() {
  const [connection, setConnection] = useState(() => ({
    state: connectionManager.getState(),
    status: connectionManager.getStatus(),
  }));
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const unsubscribe = connectionManager.subscribe((next, nextState) => {
      setConnection({ state: nextState, status: next });
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    const { state, status } = connection;
    const shouldWarn =
      (status === "disconnected" || status === "degraded") &&
      (state.consecutiveFailures > 0 || Boolean(state.lastError) || state.circuitOpen);

    if (shouldWarn) {
      if (visible) return;
      const delayMs = status === "disconnected" ? 3_500 : 8_000;
      const timer = setTimeout(() => setVisible(true), delayMs);
      return () => clearTimeout(timer);
    }

    if (visible) {
      const timer = setTimeout(() => setVisible(false), 1_500);
      return () => clearTimeout(timer);
    }

    setVisible(false);
  }, [connection, visible]);

  if (!visible) return null;

  const status = connection.status;
  const isDisconnected = status === "disconnected";
  const bg = isDisconnected ? "var(--warn)" : "var(--accent)";
  const label = isDisconnected
    ? "Backend недоступен · повторная проверка"
    : "Связь с backend нестабильна · проверяем";

  return (
    <div
      style={{
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        background: bg,
        color: "var(--surface)",
        fontSize: 12,
        fontFamily: "var(--sans)",
        padding: "6px 16px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        animation: "sync-pulse 2s ease-in-out infinite",
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: "var(--surface)",
          display: "inline-block",
        }}
      />
      {label}
    </div>
  );
}
