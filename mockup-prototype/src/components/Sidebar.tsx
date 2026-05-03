import { NavLink } from 'react-router-dom'
import { I } from './Icons'

const navItems = [
  { to: "/journal", label: "Журнал", icon: I.Pen },
  { to: "/history", label: "История", icon: I.List },
  { to: "/stats", label: "Статистика", icon: I.Bars },
  { to: "/glucose", label: "Глюкоза", icon: I.Wave },
  { to: "/database", label: "База", icon: I.Db },
  { to: "/settings", label: "Настройки", icon: I.Cog },
]

export default function Sidebar() {
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
