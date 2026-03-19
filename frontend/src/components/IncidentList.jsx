import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getIncidents, getClients, deleteIncident } from '../api'

const PRIORITY_COLORS = {
  P0: 'bg-red-600 text-white',
  P1: 'bg-orange-500 text-white',
  P2: 'bg-yellow-500 text-black',
  P3: 'bg-green-600 text-white',
}

const STATUS_COLORS = {
  DETECTING:            'bg-blue-500 text-white',
  RCA_IN_PROGRESS:      'bg-yellow-500 text-black',
  PLAYBOOK_IN_PROGRESS: 'bg-yellow-400 text-black',
  AWAITING_HIL:         'bg-orange-500 text-white',
  FIXING:               'bg-blue-600 text-white',
  RESOLVED:             'bg-green-600 text-white',
  AWAITING_MANUAL_FIX:  'bg-purple-600 text-white',
  REJECTED:             'bg-red-600 text-white',
  FIX_FAILED:           'bg-red-700 text-white',
}

function elapsed(ts, now) {
  const diff = Math.floor((now - new Date(ts)) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export default function IncidentList() {
  const [incidents, setIncidents] = useState([])
  const [clients, setClients] = useState([])
  const [filterClient, setFilterClient] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60000)
    return () => clearInterval(timer)
  }, [])

  const handleDelete = async (e, id) => {
    e.preventDefault()
    e.stopPropagation()
    if (!window.confirm('Delete this incident? This cannot be undone.')) return
    await deleteIncident(id)
    setIncidents(prev => prev.filter(i => i.id !== id))
  }

  useEffect(() => {
    getClients().then(setClients).catch(() => {})
  }, [])

  useEffect(() => {
    getIncidents({ client_id: filterClient, status: filterStatus })
      .then(setIncidents)
      .catch(() => {})
  }, [filterClient, filterStatus])

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-white mb-6">Incidents</h1>

      {/* Filters */}
      <div className="flex gap-4 mb-6">
        <select
          value={filterClient}
          onChange={e => setFilterClient(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded px-3 py-2"
        >
          <option value="">All Clients</option>
          {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded px-3 py-2"
        >
          <option value="">All Statuses</option>
          {Object.keys(STATUS_COLORS).map(s => <option key={s}>{s}</option>)}
        </select>
      </div>

      {incidents.length === 0 ? (
        <p className="text-gray-400">No incidents found.</p>
      ) : (
        <div className="space-y-3">
          {incidents.map(inc => (
            <Link
              key={inc.id}
              to={`/incidents/${inc.id}`}
              className="group block bg-gray-800 hover:bg-gray-750 border border-gray-700 rounded-lg p-4 transition"
            >
              <div className="flex items-center gap-3 mb-1">
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${PRIORITY_COLORS[inc.priority] || 'bg-gray-600 text-white'}`}>
                  {inc.priority || '—'}
                </span>
                <span className="text-white font-medium">{inc.pipeline_name || 'Unknown Pipeline'}</span>
                <span className="text-gray-500 text-xs">·</span>
                <span className="text-gray-400 text-sm">{inc.client_name}</span>
                <span className="ml-auto text-gray-500 text-xs">{elapsed(inc.created_at, now)}</span>
                <button
                  onClick={(e) => handleDelete(e, inc.id)}
                  className="text-red-500 hover:text-red-700 opacity-0 group-hover:opacity-100 transition-opacity ml-2"
                  title="Delete incident"
                >
                  🗑
                </button>
              </div>
              <div className="flex items-center gap-3">
                <span className={`px-2 py-0.5 rounded text-xs font-semibold ${STATUS_COLORS[inc.status] || 'bg-gray-500 text-white'}`}>
                  {inc.status}
                </span>
                {inc.summary && (
                  <span className="text-gray-400 text-xs truncate">{inc.summary}</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
