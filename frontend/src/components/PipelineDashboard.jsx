import React from 'react'

const TOOL_LABELS = {
  adf:        'Azure Data Factory',
  databricks: 'Databricks',
  synapse:    'Azure Synapse',
  custom:     'Custom Webhook',
}

const TOOL_SHORT = {
  adf:        'ADF',
  databricks: 'Databricks',
  synapse:    'Synapse',
  custom:     'Webhook',
}

const TOOL_ICONS = {
  adf:        '🏭',
  databricks: '⚡',
  synapse:    '🔷',
  custom:     '🔗',
}

const HEALTH_CONFIG = {
  HEALTHY:          { label: 'Healthy',          color: 'var(--green)',  bg: 'rgba(16,185,129,0.12)',  border: 'rgba(16,185,129,0.3)',  dot: '#10b981' },
  AWAITING_APPROVAL:{ label: 'Needs Approval',   color: 'var(--orange)', bg: 'rgba(245,158,11,0.12)',  border: 'rgba(245,158,11,0.3)',  dot: '#f59e0b' },
  HEALING:          { label: 'Healing…',         color: 'var(--blue)',   bg: 'rgba(59,130,246,0.12)',  border: 'rgba(59,130,246,0.3)',  dot: '#3b82f6' },
  BROKEN:           { label: 'Broken',           color: 'var(--red)',    bg: 'rgba(239,68,68,0.12)',   border: 'rgba(239,68,68,0.3)',   dot: '#ef4444' },
}

function HealthBadge({ health }) {
  const cfg = HEALTH_CONFIG[health] || HEALTH_CONFIG.HEALTHY
  return (
    <span
      className="health-badge"
      style={{
        color: cfg.color,
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
      }}
    >
      <span
        className={health === 'HEALING' ? 'health-dot pulsing' : 'health-dot'}
        style={{ background: cfg.dot }}
      />
      {cfg.label}
    </span>
  )
}

function relativeTime(isoStr) {
  if (!isoStr) return null
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function PipelineDashboard({ pipelines, onSelectPipeline }) {
  const healthy  = pipelines.filter(p => p.health === 'HEALTHY').length
  const needing  = pipelines.filter(p => p.health !== 'HEALTHY').length

  return (
    <div className="dashboard">
      {/* ── Summary bar ─────────────────────────────────────────────── */}
      <div className="dashboard-summary glass">
        <div className="summary-stat">
          <span className="summary-num">{pipelines.length}</span>
          <span className="summary-label">Pipelines</span>
        </div>
        <div className="summary-divider" />
        <div className="summary-stat">
          <span className="summary-num" style={{ color: 'var(--green)' }}>{healthy}</span>
          <span className="summary-label">Healthy</span>
        </div>
        <div className="summary-divider" />
        <div className="summary-stat">
          <span className="summary-num" style={{ color: needing > 0 ? 'var(--orange)' : 'var(--text-secondary)' }}>
            {needing}
          </span>
          <span className="summary-label">Need Attention</span>
        </div>
      </div>

      {/* ── Pipeline grid ───────────────────────────────────────────── */}
      {pipelines.length === 0 ? (
        <div className="empty-state glass" style={{ margin: '32px 0' }}>
          <div className="empty-state-icon">🔌</div>
          <h3>No Pipelines Connected</h3>
          <p>Use the <strong>Connect</strong> tab to connect your pipeline tool and auto-discover all pipelines.</p>
        </div>
      ) : (
        <div className="pipeline-grid">
          {pipelines.map(p => (
            <div
              key={p.id}
              className={`pipeline-grid-card glass ${p.health !== 'HEALTHY' ? 'pipeline-grid-card-alert' : ''}`}
              onClick={() => onSelectPipeline && onSelectPipeline(p)}
              style={{
                borderColor: p.health === 'AWAITING_APPROVAL'
                  ? 'rgba(245,158,11,0.35)'
                  : p.health === 'BROKEN'
                  ? 'rgba(239,68,68,0.35)'
                  : p.health === 'HEALING'
                  ? 'rgba(59,130,246,0.35)'
                  : undefined,
              }}
            >
              {/* Card header */}
              <div className="pgc-header">
                <span className="pgc-tool-icon">{TOOL_ICONS[p.tool] || '📦'}</span>
                <div className="pgc-meta">
                  <div className="pgc-name">{p.name}</div>
                  <div className="pgc-tool">{TOOL_LABELS[p.tool] || p.tool}</div>
                </div>
                <HealthBadge health={p.health || 'HEALTHY'} />
              </div>

              {/* Active incident info */}
              {p.active_incident_id && (
                <div className="pgc-incident">
                  <span className="pgc-incident-id">{p.active_incident_id}</span>
                  {p.active_incident_priority && (
                    <span className={`priority-badge p${p.active_incident_priority?.toLowerCase()}`}>
                      {p.active_incident_priority}
                    </span>
                  )}
                  {p.active_incident_summary && (
                    <div className="pgc-incident-summary">{p.active_incident_summary}</div>
                  )}
                </div>
              )}

              {/* Footer */}
              <div className="pgc-footer">
                <span className="pgc-created">{relativeTime(p.created_at)}</span>
                {p.health !== 'HEALTHY' && (
                  <span className="pgc-action-hint">Click to review →</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
