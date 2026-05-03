# glucotracker — clickable prototype

Clickable frontend prototype built from the `mockup/` design artboards. No backend, fake data only.

## Run

```bash
cd mockup-prototype
npm install
npm run dev     # http://localhost:5173
npm run build   # production build → dist/
```

## Routes

| Route       | Page          |
|-------------|---------------|
| `/journal`  | Журнал        |
| `/history`  | История       |
| `/glucose`  | Глюкоза       |
| `/stats`    | Статистика    |
| `/database` | База          |
| `/settings` | Настройки     |

## How mockup files map to prototype components

| Mockup file           | Prototype file(s)                                                |
|-----------------------|------------------------------------------------------------------|
| `styles.css`          | `src/styles.css` — copied with minor additions                   |
| `icons.jsx`           | `src/components/Icons.tsx` — same SVG paths, typed exports       |
| `shell.jsx`           | `src/components/AppShell.tsx` + `Sidebar.tsx` + `PageHead.tsx`   |
| `panels.jsx`          | `src/components/AutocompletePanel.tsx`, `SelectedMealPanel.tsx`, `DbItemPanel.tsx` |
| `other-pages.jsx`     | `src/pages/JournalPage.tsx`, `HistoryPage.tsx`, `DatabasePage.tsx`, `SettingsPage.tsx` |
| `glucose.jsx`         | `src/pages/GlucosePage.tsx`                                      |
| `stats (1).jsx`       | `src/pages/StatsPage.tsx`                                        |
| `design-canvas (1).jsx` | not used (artboard wrapper, not needed for clickable prototype) |

## Interactive features

- **Sidebar** — NavLink routing, active state highlight
- **Journal** — click meal row to open right panel with details; type in input bar to show autocomplete panel
- **History** — expandable episode cards; click inner rows to open meal detail panel
- **Database** — click product row to open detail panel; tab filtering
- **Glucose** — Raw/Normalized/Smoothed toggle; time range selector (3H–7D); Episodes/Events tab switch; expandable episodes with sub-items
- **Stats** — full data display with carbs chart, balance chart, glucose sparkline, heatmap, quality footer
- **Settings** — clickable checkboxes, theme switcher, editable fields

## Notes

- Original mockup files in `mockup/` are untouched
- No backend connections — all data is fake
- No changes to the real Tauri/desktop app
