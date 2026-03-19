/**
 * api.js
 * ------
 * All backend communication. Base URL defaults to localhost:8000.
 */

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function _fetch(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const b = await res.json(); detail = b.detail || detail } catch (_) {}
    throw new Error(detail)
  }
  if (res.status === 204) return null
  return res.json()
}

// ── Clients ────────────────────────────────────────────────────────────────
export const getClients        = ()       => _fetch('/clients')
export const createClient      = (data)   => _fetch('/clients', { method: 'POST', body: JSON.stringify(data) })
export const deleteClient      = (id)     => _fetch(`/clients/${id}`, { method: 'DELETE' })

// ── Incidents ──────────────────────────────────────────────────────────────
export const getIncidents      = (params = {}) => {
  const qs = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v))
  ).toString()
  return _fetch(`/incidents${qs ? '?' + qs : ''}`)
}
export const getIncident       = (id)     => _fetch(`/incidents/${id}`)
export const deleteIncident    = (id)     => _fetch(`/incidents/${id}`, { method: 'DELETE' })

// ── HIL ────────────────────────────────────────────────────────────────────
export const submitHILDecision = (incident_id, decision, engineer_email, db_credentials = null) =>
  _fetch('/hil/decision', {
    method: 'POST',
    body: JSON.stringify({
      incident_id,
      decision,
      engineer_email,
      ...(db_credentials && { db_credentials }),
    }),
  })

// ── Notifications ──────────────────────────────────────────────────────────
export const getNotifications  = ()  => _fetch('/notifications')
export const markRead          = (id) => _fetch(`/notifications/${id}/read`, { method: 'POST' })
