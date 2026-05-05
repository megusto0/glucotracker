# Design Tokens

These shared tokens define the initial white, off-white, restrained visual system for the Tauri desktop client and the future Android client.

## Colors

| CSS Variable | Value     | Use                         |
| ------------ | --------- | --------------------------- |
| `--bg`       | `#F6F4EE` | App background              |
| `--surface`  | `#FFFFFF` | Cards, panels, and controls |
| `--fg`       | `#0A0A0A` | Primary text                |
| `--muted`    | `#77736A` | Secondary text and metadata |
| `--hairline` | `#D8D3C8` | Dividers and borders        |
| `--accent`   | `#A4652A` | Primary accent              |
| `--danger`   | `#9F2A20` | Error and destructive state |
| `--ok`       | `#2F6B3F` | Success state               |

## Typography

| Token          | Value                           |
| -------------- | ------------------------------- |
| Body           | Inter or system-ui fallback     |
| Numbers        | JetBrains Mono or ui-monospace  |
| Product labels | Uppercase, letter spacing `+6%` |
| Page title     | `56px` desktop, `40px` compact  |
| Card number    | `40px`                          |
| Body           | `15px`                          |
| Meta           | `12px`                          |

## Layout

| Token        | Value         |
| ------------ | ------------- |
| Grid         | 8pt           |
| Left rail    | `64px`        |
| Section gaps | `72px`        |
| Item gaps    | `16px`        |
| Card radius  | `0-4px`       |
| Card shape   | Squared cards |

## Motion

- Duration: `180-250ms`.
- Easing: ease-out.
- Allowed motion: fade, small vertical shift, lateral panel slide.
- Avoid glow, blur, glassmorphism, and gradients.
