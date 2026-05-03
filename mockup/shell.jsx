/* global React, I */

// ───── shared sidebar shell ─────
function Shell({ active = "Журнал", children, rightPanel = null }) {
  const items = [
    { k: "Журнал", icon: "Pen" },
    { k: "История", icon: "List" },
    { k: "Статистика", icon: "Bars" },
    { k: "Глюкоза", icon: "Wave" },
    { k: "База", icon: "Db" },
    { k: "Настройки", icon: "Cog" },
  ];
  return (
    <div className="gt-app">
      <aside className="gt-sidebar">
        <div className="gt-brand">
          <span className="gt-dot" />
          <span>gluco<b>tracker</b></span>
        </div>
        <nav className="gt-nav">
          {items.map((it) => {
            const Ic = I[it.icon];
            return (
              <a key={it.k} className={it.k === active ? "active" : ""}>
                <Ic />
                <span>{it.k}</span>
              </a>
            );
          })}
        </nav>
        <div className="gt-side-foot">
          <div className="gt-avatar">gl</div>
          <div className="col" style={{ lineHeight: 1.3 }}>
            <span style={{ color: "var(--ink)", fontWeight: 500 }}>glucotracker</span>
            <span style={{ fontSize: 10 }}>локально · v0.4</span>
          </div>
        </div>
      </aside>
      <main className="gt-main">{children}</main>
      {rightPanel && (
        <aside className="gt-rightpanel">
          {rightPanel}
        </aside>
      )}
    </div>
  );
}

function PageHead({ crumbs = [], title, right }) {
  return (
    <div className="row" style={{ alignItems: "flex-end", justifyContent: "space-between", gap: 24, marginBottom: 22 }}>
      <div>
        <div className="gt-crumbs">
          {crumbs.map((c, i) => <span key={i}>{c}</span>)}
        </div>
        <h1 className="gt-h1">{title}</h1>
      </div>
      {right && <div>{right}</div>}
    </div>
  );
}

// ───── tiny chart helpers (SVG) ─────
function BarChart({ data, w = 560, h = 130, color = "var(--accent)", emptyColor = "var(--hairline)", showAxis = true, max }) {
  const m = max ?? Math.max(...data.map((d) => d.v), 1);
  const pad = { l: 28, r: 8, t: 6, b: 18 };
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;
  const bw = innerW / data.length;
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      {/* y-axis ticks */}
      {showAxis && [0, 0.5, 1].map((p, i) => (
        <g key={i}>
          <line x1={pad.l} x2={w - pad.r} y1={pad.t + innerH * (1 - p)} y2={pad.t + innerH * (1 - p)}
            stroke="var(--hairline)" strokeDasharray={p === 0 ? "0" : "2 3"} />
          <text x={pad.l - 6} y={pad.t + innerH * (1 - p) + 3} textAnchor="end"
            fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">{Math.round(m * p)}</text>
        </g>
      ))}
      {data.map((d, i) => {
        const v = (d.v / m) * innerH;
        const x = pad.l + i * bw + bw * 0.18;
        const y = pad.t + innerH - v;
        const isToday = d.today;
        return (
          <rect key={i} x={x} y={y} width={bw * 0.64} height={Math.max(v, 1)}
            fill={d.v === 0 ? emptyColor : (isToday ? "var(--ink)" : color)} />
        );
      })}
      {showAxis && (
        <>
          <text x={pad.l} y={h - 4} fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">{data[0]?.lbl}</text>
          <text x={w - pad.r} y={h - 4} textAnchor="end" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-4)">{data[data.length - 1]?.lbl}</text>
        </>
      )}
    </svg>
  );
}

// ── Sparkline / line ──
function buildSpline(points, w, h, padL = 0, padR = 0, padT = 0, padB = 0, yMin, yMax) {
  if (!points || !points.length) return "";
  const min = yMin ?? Math.min(...points.map((p) => p.y));
  const max = yMax ?? Math.max(...points.map((p) => p.y));
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  return points.map((p, i) => {
    const x = padL + (i / (points.length - 1)) * innerW;
    const y = padT + innerH - ((p.y - min) / (max - min || 1)) * innerH;
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

window.Shell = Shell;
window.PageHead = PageHead;
window.BarChart = BarChart;
window.buildSpline = buildSpline;
