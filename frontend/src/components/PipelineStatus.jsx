import React, { useState } from 'react'
import { triggerPipeline } from '../api.js'

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function StatusBadge({ status }) {
  const labels = {
    HEALTHY: 'Healthy',
    BROKEN: 'Broken',
    HEALING: 'Healing',
    AWAITING_APPROVAL: 'Awaiting Approval',
  }
  return (
    <span className={`status-badge ${status}`}>
      {labels[status] ?? status}
    </span>
  )
}

export default function PipelineStatus({ status, onRefresh }) {
  const [triggering, setTriggering] = useState(false)

  async function handleTrigger() {
    setTriggering(true)
    try {
      await triggerPipeline()
      if (onRefresh) await onRefresh()
    } catch (err) {
      console.error('Trigger failed:', err)
    } finally {
      setTriggering(false)
    }
  }

  const healthPct = status?.system_health_pct ?? 100
  const activeIncidents = status?.active_incidents ?? 0
  const lastRun = status?.last_run ? formatTime(status.last_run) : 'Never'

  return (
    <div className="pipeline-status glass">
      <div className="pipeline-status-inner">
        {/* Name + status badge */}
        <div className="pipeline-name-group">
          <span className="pipeline-label">Pipeline</span>
          <span className="pipeline-name">Sales ETL Pipeline</span>
        </div>

        {status && <StatusBadge status={status.status} />}

        <div className="pipeline-divider" />

        {/* Metric cards */}
        <div className="metrics-row">
          <div className="metric-card">
            <div className="metric-label">System Health</div>
            <div
              className={`metric-value ${
                healthPct >= 80 ? 'healthy' : healthPct >= 50 ? 'warning' : 'danger'
              }`}
            >
              {healthPct}%
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Active Incidents</div>
            <div
              className={`metric-value ${
                activeIncidents === 0 ? 'healthy' : activeIncidents <= 2 ? 'warning' : 'danger'
              }`}
            >
              {activeIncidents}
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Last Run</div>
            <div className="metric-value" style={{ fontSize: '13px' }}>
              {lastRun}
            </div>
          </div>
        </div>

        {/* Trigger button */}
        <button
          className="trigger-btn"
          onClick={handleTrigger}
          disabled={triggering}
        >
          {triggering ? (
            <>
              <span>Running…</span>
            </>
          ) : (
            <>
              <span>▶</span>
              <span>Trigger Pipeline</span>
            </>
          )}
        </button>
      </div>
    </div>
  )
}
