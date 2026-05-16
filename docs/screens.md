# Screens And Routes

Status: source of truth
Last updated: 2026-05-13
Owner/area: desktop routes, Android navigation

All user-facing copy is Russian. Where a feature is absent on mobile, render the
dotted hint `Доступно в десктоп-версии.` per `CONCEPT.md` §2 instead of silently
hiding the capability.

## Desktop Routes

Routes are defined in `desktop/src/app/routes.tsx`.

| Route | Component | Responsibility |
| --- | --- | --- |
| `/login` | `LoginPage` | Username/password login for seeded users. |
| `/` | `ChatPage` | Journal: selected day, meal entry, photo/Gemini draft review, accepted/draft rows, selected-meal panel. |
| `/feed` | `FeedPage` | History/timeline projection of accepted food episodes and context events. |
| `/stats` | `StatsPage` | Nutrition, day rhythm, insights, sparse-data summaries, calorie/TDEE context. |
| `/glucose` | `GlucosePage` | Glucose dashboard, CGM ranges, sensor/fingerstick context. Gluco-only feature. |
| `/database` | `DatabasePage` | Product/template browsing, saved products, local product actions. |
| `/settings` | `SettingsPage` | Backend connection, Nightscout settings, activity/profile, PDF report, TXT export. |

## Desktop Shell

`Shell.tsx` renders the fixed sidebar, main scroll area, and route content.
`Sidebar.tsx` owns navigation and the mini glucose widget when backend data is
available. Page components own page padding and local layout.

## Android Auth Gate

`GlucotrackerApp` shows:

- loading blank warm background while token state is read;
- `LoginRoute` when signed out;
- `SignedInApp` once authenticated.

Tokens are stored through `TokenStore` with `EncryptedSharedPreferences`.

## Android Shared Routes

Routes are defined in `ui/navigation/Routes.kt` and `GTNavHost.kt`.

| Route | Responsibility |
| --- | --- |
| `today` and `today/{date}` | Today page. Also hosts the Stats pager as page 2. |
| `history` | History list/search/filter surface. |
| `base` | Product/template base. |
| `more` | Settings, goals, schedule/rhythm, logout, flavor-provided sections. |
| `outbox?focus={id}` | Outbox inspector and retry/delete/reconciliation UI. |
| `record/{id}` | Meal detail and fast edit surface. |
| `photo_capture` | Camera capture route. |

The capture FAB opens `GTComposeSheet`; it is not a bottom-tab destination.

## Android Flavor Tabs

Gluco flavor (`src/gluco/.../GlucoFlavorModule.kt`):

- Today
- Glucose
- History
- More

Food flavor (`src/food/.../FoodFlavorModule.kt`):

- Today
- History
- Base
- More

Food flavor has no glucose tab and receives no real Nightscout/glucose surfaces.

## Screen Rules

- Today headline totals show backend-accepted totals only; pending rows are
  separate context.
- Stats uses sparse-data summaries when there are too few tracked days.
- History is a projection over meals/context; do not merge accepted meals to
  manufacture history rows.
- Glucose surfaces are display-only over immutable raw CGM.
- Settings is the desktop owner for Nightscout URL/secret, OpenAPI, PDF, and TXT
  exports.

## Needs Verification

- The original mobile concept (`CONCEPT.md` §3) specified five tabs plus central
  FAB. Current code has four tabs per flavor plus the FAB, with Stats inside
  Today. This is intentional in current code but should be reflected in future
  product specs before treating the old concept as current navigation source.
