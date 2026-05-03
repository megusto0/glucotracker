import { ReactNode } from 'react'
import Sidebar from './Sidebar'

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="gt-app">
      <Sidebar />
      <main className="gt-main">{children}</main>
    </div>
  )
}
