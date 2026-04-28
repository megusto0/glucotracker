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
};
