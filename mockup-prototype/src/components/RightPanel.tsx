import { ReactNode } from 'react'

export default function RightPanel({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  return (
    <aside className="gt-rightpanel">
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
        <button className="btn icon" onClick={onClose} style={{ border: 'none', background: 'transparent', fontSize: 18, cursor: 'pointer', color: 'var(--ink-3)' }}>
          ×
        </button>
      </div>
      {children}
    </aside>
  )
}
