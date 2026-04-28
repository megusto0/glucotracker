import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { server } from "./msw";
import { useSettingsStore } from "../features/settings/settingsStore";

Object.defineProperty(URL, "createObjectURL", {
  configurable: true,
  value: vi.fn(() => "blob:glucotracker-test"),
});

Object.defineProperty(URL, "revokeObjectURL", {
  configurable: true,
  value: vi.fn(),
});

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  server.resetHandlers();
  cleanup();
  localStorage.clear();
  useSettingsStore.setState({
    baseUrl: "http://127.0.0.1:8000",
    token: "",
  });
  window.history.pushState({}, "", "/");
});

afterAll(() => server.close());
