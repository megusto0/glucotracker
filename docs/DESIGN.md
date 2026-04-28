\# glucotracker DESIGN.md



\## Product feeling



glucotracker is a personal food diary and meal ledger. It is not a hospital app, not a messenger, and not a generic SaaS dashboard.



The UI should feel like:

\- white-background YEEZY-style catalog

\- minimal product ledger

\- receipt/logbook

\- quiet futuristic nutrition journal

\- desktop-first utility



\## Visual direction



Use:

\- off-white background

\- black text

\- thin borders

\- huge typography

\- sparse layout

\- product-like cards only where necessary

\- compact ledger rows

\- right-side contextual panel

\- mono numbers for carbs/kcal/macros



Avoid:

\- dark theme

\- medical blue

\- glassmorphism

\- gradients

\- shadows

\- big rounded SaaS cards

\- colorful dashboards

\- chat bubbles

\- cute food app visuals

\- mobile-first layout



\## Colors



\--bg: #F7F5EF

\--surface: #FFFFFF

\--fg: #0A0A0A

\--muted: #7A766D

\--line: #D8D2C4

\--accent: #B8842D

\--danger: #B3261E

\--success: #3C7A3F



\## Typography



Body: Inter or system-ui

Numbers: JetBrains Mono or ui-monospace

Page title: 56px

Card number: 36px

Body: 15px

Meta: 11px



\## Layout



Desktop-first.

Target: 1440x900.

Left rail: 72px.

Main content: flexible.

Right panel: 360px.

No centered app card.

No phone-first layout.



\## Main screen



The main screen is not a chat messenger. It is a daily food ledger with a bottom input.



Rows look like:



09:20   coffee + protein bar ................. 22C   310 kcal

13:45   bk:whopper + fries\_m ................. 98C   1120 kcal

20:10   chicken potato greens ................ 66C   710 kcal



\## Key interactions



\- typing bk: opens right autocomplete panel

\- selected items become chips

\- pasted photos create a meal draft

\- meal draft appears in right panel

\- every estimate has source, confidence, evidence, assumptions

\- totals are visually dominant

\- accept/edit/discard are always visible



\## Rule



Backend is the product.

Frontend is replaceable.

The UI must consume API-shaped data and keep business logic out of components.

