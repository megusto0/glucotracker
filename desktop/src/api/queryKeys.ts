export const queryKeys = {
  health: ["health"] as const,
  meals: (filters: Record<string, unknown>) => ["meals", filters] as const,
  feedMeals: (filters: Record<string, unknown>) =>
    ["feed-meals", filters] as const,
  dashboardToday: ["dashboard", "today"] as const,
  dashboardRange: (from: string, to: string) =>
    ["dashboard", "range", from, to] as const,
  dashboardHeatmap: (weeks: number) => ["dashboard", "heatmap", weeks] as const,
  dashboardTopPatterns: (days: number, limit: number) =>
    ["dashboard", "top-patterns", days, limit] as const,
  dashboardSourceBreakdown: (days: number) =>
    ["dashboard", "source-breakdown", days] as const,
  dashboardDataQuality: (days: number) =>
    ["dashboard", "data-quality", days] as const,
  nightscoutStatus: ["nightscout", "status"] as const,
  nightscoutSettings: ["nightscout", "settings"] as const,
  nightscoutDayStatus: (date: string) =>
    ["nightscout", "day-status", date] as const,
  nightscoutEvents: (from: string, to: string) =>
    ["nightscout", "events", from, to] as const,
  timeline: (from: string, to: string) => ["timeline", from, to] as const,
  glucoseDashboard: (from: string, to: string, mode: string) =>
    ["glucose", "dashboard", from, to, mode] as const,
  sensors: ["glucose", "sensors"] as const,
  fingersticks: (from?: string, to?: string) =>
    ["glucose", "fingersticks", from, to] as const,
};
