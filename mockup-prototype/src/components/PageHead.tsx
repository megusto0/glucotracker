import { ReactNode } from 'react'

export default function PageHead({ crumbs = [], title, right }: {
  crumbs?: string[]; title: string; right?: ReactNode
}) {
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
  )
}
