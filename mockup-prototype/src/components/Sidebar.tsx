import { NavLink, useNavigate } from 'react-router-dom'
import { I } from './Icons'

const navItems = [
  { to: "/journal", label: "Журнал", icon: I.Pen },
  { to: "/history", label: "История", icon: I.List },
  { to: "/stats", label: "Статистика", icon: I.Bars },
  { to: "/glucose", label: "Глюкоза", icon: I.Wave },
  { to: "/database", label: "База", icon: I.Db },
  { to: "/settings", label: "Настройки", icon: I.Cog },
]

// Mini sparkline data: last 12 readings
const miniTrend = [6.2, 6.8, 7.4, 8.1, 8.6, 9.0, 9.3, 9.5, 9.6, 9.7, 9.8, 9.8]

function MiniSparkline() {
  const w = 80, h = 22
  const min = Math.min(...miniTrend), max = Math.max(...miniTrend)
  const range = max - min || 1
  const path = miniTrend.map((y, i) => {
    const x = (i / (miniTrend.length - 1)) * w
    const yy = h - ((y - min) / range) * h
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${yy.toFixed(1)}`
  }).join(' ')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: 'block' }}>
      <path d={path} fill="none" stroke="var(--ink)" strokeWidth="1.2" />
      <circle cx={w} cy={h - ((miniTrend[miniTrend.length - 1] - min) / range) * h} r="2" fill="var(--accent)" />
    </svg>
  )
}

export default function Sidebar() {
  const navigate = useNavigate()
  return (
    <aside className="gt-sidebar">
      <div className="gt-brand">
        <span className="gt-dot" />
        <span>gluco<b>tracker</b></span>
      </div>
      <nav className="gt-nav">
        {navItems.map((it) => {
          const Ic = it.icon
          return (
            <NavLink key={it.to} to={it.to} className={({ isActive }) => isActive ? "active" : ""}>
              <Ic />
              <span>{it.label}</span>
            </NavLink>
          )
        })}
      </nav>

      {/* Live glucose widget — visible on every page */}
      <div
        className="gt-side-glucose"
        onClick={() => navigate('/glucose')}
        title="Перейти к графику глюкозы"
      >
        <div className="row" style={{ alignItems: 'baseline', justifyContent: 'space-between' }}>
          <span className="lbl">сейчас</span>
          <span className="mono" style={{ fontSize: 9, color: 'var(--ink-4)' }}>2 мин назад</span>
        </div>
        <div className="row" style={{ alignItems: 'baseline', gap: 4, marginTop: 4 }}>
          <span className="mono" style={{ fontSize: 22, fontWeight: 500, letterSpacing: '-0.01em' }}>9,8</span>
          <span style={{ fontSize: 10, color: 'var(--ink-3)' }}>ммоль/л</span>
          <span className="spacer" />
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2, fontSize: 10, color: 'var(--accent)', fontFamily: 'var(--mono)' }}>
            <I.Up size={9} /> +0,6
          </span>
        </div>
        <div style={{ marginTop: 6 }}>
          <MiniSparkline />
        </div>
        <div className="mono" style={{ fontSize: 9, color: 'var(--ink-4)', marginTop: 4, textAlign: 'right' }}>
          последние 60 мин
        </div>
      </div>

      <div className="gt-side-foot">
        <div className="gt-avatar">gl</div>
        <div className="col" style={{ lineHeight: 1.3 }}>
          <span style={{ color: "var(--ink)", fontWeight: 500 }}>glucotracker</span>
          <span style={{ fontSize: 10 }}>локально · v0.4</span>
        </div>
      </div>
    </aside>
  )
}
