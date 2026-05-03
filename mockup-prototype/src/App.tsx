import { Routes, Route, Navigate } from 'react-router-dom'
import AppShell from './components/AppShell'
import JournalPage from './pages/JournalPage'
import HistoryPage from './pages/HistoryPage'
import GlucosePage from './pages/GlucosePage'
import StatsPage from './pages/StatsPage'
import DatabasePage from './pages/DatabasePage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/journal" element={<JournalPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/glucose" element={<GlucosePage />} />
        <Route path="/stats" element={<StatsPage />} />
        <Route path="/database" element={<DatabasePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/journal" replace />} />
      </Routes>
    </AppShell>
  )
}
