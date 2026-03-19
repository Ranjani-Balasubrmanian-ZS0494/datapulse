import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import ClientList from './components/ClientList'
import IncidentList from './components/IncidentList'
import IncidentDetail from './components/IncidentDetail'
import NotificationBell from './components/NotificationBell'

function Nav() {
  const linkClass = ({ isActive }) =>
    `px-3 py-2 rounded text-sm font-medium transition ${
      isActive ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-700'
    }`
  return (
    <header className="bg-gray-900 border-b border-gray-800 sticky top-0 z-40">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center gap-6">
        <span className="text-white font-bold text-lg tracking-tight">SHDP</span>
        <nav className="flex items-center gap-1 flex-1">
          <NavLink to="/clients"   className={linkClass}>Clients</NavLink>
          <NavLink to="/incidents" className={linkClass}>Incidents</NavLink>
        </nav>
        <NotificationBell />
      </div>
    </header>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <Nav />
        <main className="max-w-6xl mx-auto">
          <Routes>
            <Route path="/"                    element={<Navigate to="/incidents" replace />} />
            <Route path="/clients"             element={<ClientList />} />
            <Route path="/incidents"           element={<IncidentList />} />
            <Route path="/incidents/:id"       element={<IncidentDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
