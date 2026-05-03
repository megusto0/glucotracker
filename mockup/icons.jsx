/* global React */

// ───── Lucide-style line icons (24 stroke 1.6) ─────
const Icon = ({ d, size = 16, sw = 1.6, fill = "none", style }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill={fill}
    stroke="currentColor"
    strokeWidth={sw}
    strokeLinecap="round"
    strokeLinejoin="round"
    style={style}
    aria-hidden="true"
  >
    {typeof d === "string" ? <path d={d} /> : d}
  </svg>
);

const I = {
  Pen: (p) => <Icon {...p} d={
    <>
      <path d="M12 20h9"/>
      <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>
    </>
  } />,
  List: (p) => <Icon {...p} d={
    <>
      <line x1="8" y1="6" x2="21" y2="6"/>
      <line x1="8" y1="12" x2="21" y2="12"/>
      <line x1="8" y1="18" x2="21" y2="18"/>
      <circle cx="4" cy="6" r="0.8"/>
      <circle cx="4" cy="12" r="0.8"/>
      <circle cx="4" cy="18" r="0.8"/>
    </>
  } />,
  Bars: (p) => <Icon {...p} d={
    <>
      <line x1="3" y1="20" x2="3" y2="10"/>
      <line x1="9" y1="20" x2="9" y2="4"/>
      <line x1="15" y1="20" x2="15" y2="14"/>
      <line x1="21" y1="20" x2="21" y2="8"/>
    </>
  } />,
  Wave: (p) => <Icon {...p} d={
    <>
      <path d="M2 14c2 0 3-6 5-6s3 10 5 10 3-12 5-12 3 6 5 6"/>
    </>
  } />,
  Db: (p) => <Icon {...p} d={
    <>
      <ellipse cx="12" cy="5" rx="8" ry="3"/>
      <path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/>
      <path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"/>
    </>
  } />,
  Cog: (p) => <Icon {...p} d={
    <>
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h0a1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>
    </>
  } />,
  ArrowR: (p) => <Icon {...p} d="M5 12h14M13 6l6 6-6 6"/>,
  ArrowU: (p) => <Icon {...p} d="M12 19V5M5 12l7-7 7 7"/>,
  ChevL: (p) => <Icon {...p} d="M15 18l-6-6 6-6"/>,
  ChevR: (p) => <Icon {...p} d="M9 18l6-6-6-6"/>,
  ChevD: (p) => <Icon {...p} d="M6 9l6 6 6-6"/>,
  More: (p) => <Icon {...p} d={
    <>
      <circle cx="12" cy="5" r="1"/>
      <circle cx="12" cy="12" r="1"/>
      <circle cx="12" cy="19" r="1"/>
    </>
  } />,
  Plus: (p) => <Icon {...p} d="M12 5v14M5 12h14"/>,
  Camera: (p) => <Icon {...p} d={
    <>
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
      <circle cx="12" cy="13" r="4"/>
    </>
  } />,
  Search: (p) => <Icon {...p} d={
    <>
      <circle cx="11" cy="11" r="7"/>
      <path d="m20 20-3.5-3.5"/>
    </>
  } />,
  Check: (p) => <Icon {...p} d="M5 12l5 5 9-11"/>,
  Wifi: (p) => <Icon {...p} d={
    <>
      <path d="M2 8.82a15 15 0 0 1 20 0"/>
      <path d="M5 12.86a10 10 0 0 1 14 0"/>
      <path d="M8.5 16.5a5 5 0 0 1 7 0"/>
      <line x1="12" y1="20" x2="12" y2="20.01"/>
    </>
  } />,
  Refresh: (p) => <Icon {...p} d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5"/>,
  Trash: (p) => <Icon {...p} d={
    <>
      <polyline points="3 6 5 6 21 6"/>
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
      <path d="M10 11v6M14 11v6"/>
    </>
  } />,
  Cal: (p) => <Icon {...p} d={
    <>
      <rect x="3" y="4" width="18" height="18" rx="2"/>
      <line x1="16" y1="2" x2="16" y2="6"/>
      <line x1="8" y1="2" x2="8" y2="6"/>
      <line x1="3" y1="10" x2="21" y2="10"/>
    </>
  } />,
  Edit: (p) => <Icon {...p} d={
    <>
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </>
  } />,
  Filter: (p) => <Icon {...p} d="M3 4h18l-7 9v6l-4 2v-8z"/>,
  Photo: (p) => <Icon {...p} d={
    <>
      <rect x="3" y="3" width="18" height="18" rx="2"/>
      <circle cx="9" cy="9" r="2"/>
      <path d="m21 15-5-5L5 21"/>
    </>
  } />,
  Drop: (p) => <Icon {...p} d={
    <>
      <path d="M12 2.69 5.64 9.05a9 9 0 1 0 12.72 0z"/>
    </>
  } />,
  Send: (p) => <Icon {...p} d={
    <>
      <path d="M22 2L11 13"/>
      <path d="M22 2l-7 20-4-9-9-4 20-7z"/>
    </>
  } />,
  Lock: (p) => <Icon {...p} d={
    <>
      <rect x="3" y="11" width="18" height="11" rx="2"/>
      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </>
  } />,
  Sun: (p) => <Icon {...p} d={
    <>
      <circle cx="12" cy="12" r="4"/>
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
    </>
  } />,
  Moon: (p) => <Icon {...p} d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>,
  Clock: (p) => <Icon {...p} d={
    <>
      <circle cx="12" cy="12" r="9"/>
      <path d="M12 7v5l3 2"/>
    </>
  } />,
  Up: (p) => <Icon {...p} d="M5 14l7-7 7 7"/>,
  Down: (p) => <Icon {...p} d="M5 10l7 7 7-7"/>,
  Pkg: (p) => <Icon {...p} d={
    <>
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
      <line x1="12" y1="22.08" x2="12" y2="12"/>
    </>
  } />,
  X: (p) => <Icon {...p} d="M6 6l12 12M18 6L6 18"/>,
  Bolt: (p) => <Icon {...p} d="M13 2L3 14h7l-1 8 10-12h-7l1-8z"/>,
  Flame: (p) => <Icon {...p} d="M12 22s7-5.5 7-12c0-3-2-5-3-5 1 4-3 5-3 9 0-3-3-2-3-5 0 2-2 3-2 6 0 4 4 7 4 7z"/>,
  Sparkles: (p) => <Icon {...p} d={
    <>
      <path d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z"/>
      <path d="M19 14l.7 1.8L21.5 16.5l-1.8.7L19 19l-.7-1.8L16.5 16.5l1.8-.7z"/>
    </>
  } />,
  Activity: (p) => <Icon {...p} d="M22 12h-4l-3 9L9 3l-3 9H2"/>,
};

window.I = I;
window.Icon = Icon;
