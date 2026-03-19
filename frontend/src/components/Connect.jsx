import React, { useState } from 'react'
import { connectAndDiscover } from '../api.js'

// ---------------------------------------------------------------------------
// Credential field definitions per tool
// ---------------------------------------------------------------------------
const TOOL_FIELDS = {
  adf: [
    { key: 'tenant_id',       label: 'Tenant ID',       placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
    { key: 'client_id',       label: 'Client ID',       placeholder: 'Service principal app ID' },
    { key: 'client_secret',   label: 'Client Secret',   placeholder: 'Service principal secret', secret: true },
    { key: 'subscription_id', label: 'Subscription ID', placeholder: 'Azure subscription ID' },
    { key: 'resource_group',  label: 'Resource Group',  placeholder: 'my-resource-group' },
    { key: 'factory_name',    label: 'Factory Name',    placeholder: 'my-adf-factory' },
  ],
  databricks: [
    { key: 'host',  label: 'Workspace Host URL', placeholder: 'https://adb-xxxx.azuredatabricks.net' },
    { key: 'token', label: 'Access Token',       placeholder: 'dapi...', secret: true },
  ],
  synapse: [
    { key: 'tenant_id',      label: 'Tenant ID',       placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
    { key: 'client_id',      label: 'Client ID',       placeholder: 'Service principal app ID' },
    { key: 'client_secret',  label: 'Client Secret',   placeholder: 'Service principal secret', secret: true },
    { key: 'subscription_id',label: 'Subscription ID', placeholder: 'Azure subscription ID' },
    { key: 'resource_group', label: 'Resource Group',  placeholder: 'my-resource-group' },
    { key: 'workspace_name', label: 'Workspace Name',  placeholder: 'my-synapse-workspace' },
  ],
  custom: [
    { key: 'webhook_url', label: 'Webhook URL',          placeholder: 'https://your-system.com/rerun' },
    { key: 'headers',     label: 'Extra Headers (JSON)', placeholder: '{"Authorization": "Bearer token"}' },
  ],
}

const TOOL_LABELS = {
  adf:        'Azure Data Factory',
  databricks: 'Databricks',
  synapse:    'Azure Synapse',
  custom:     'Custom Webhook',
}

const TOOL_ICONS = {
  adf:        '🏭',
  databricks: '⚡',
  synapse:    '🔷',
  custom:     '🔗',
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Connect({ onConnected }) {
  const [tool, setTool]             = useState('adf')
  const [creds, setCreds]           = useState({})
  const [sourceConn, setSourceConn] = useState('')
  const [targetConn, setTargetConn] = useState('')
  const [notifyEmail, setNotifyEmail] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [result, setResult]         = useState(null)  // null | {ok, data, message}

  const handleToolChange = (t) => {
    setTool(t)
    setCreds({})
    setResult(null)
  }

  const handleCred = (key, val) => setCreds(c => ({ ...c, [key]: val }))

  const handleConnect = async (e) => {
    e.preventDefault()
    setConnecting(true)
    setResult(null)
    try {
      const data = await connectAndDiscover({
        tool,
        tool_credentials: creds,
        source_db_conn: sourceConn,
        target_db_conn: targetConn,
        notify_email: notifyEmail,
      })
      setResult({ ok: true, data })
      if (onConnected) onConnected(data.pipelines)
    } catch (err) {
      setResult({ ok: false, message: err.message })
    } finally {
      setConnecting(false)
    }
  }

  const fields = TOOL_FIELDS[tool] || []

  return (
    <div className="connect-page">
      <div className="connect-hero">
        <div className="connect-hero-icon">⚡</div>
        <h1 className="connect-hero-title">Connect Your Pipeline Tool</h1>
        <p className="connect-hero-sub">
          Enter your credentials once. The platform auto-discovers all your pipelines,
          monitors them continuously, and self-heals failures using AI — with your approval.
        </p>
      </div>

      {/* Tool selector */}
      <div className="tool-selector">
        {Object.entries(TOOL_LABELS).map(([val, label]) => (
          <button
            key={val}
            className={`tool-tile ${tool === val ? 'tool-tile-active' : ''}`}
            onClick={() => handleToolChange(val)}
            type="button"
          >
            <span className="tool-tile-icon">{TOOL_ICONS[val]}</span>
            <span className="tool-tile-label">{label}</span>
          </button>
        ))}
      </div>

      {/* Credentials form */}
      <div className="connect-form-wrap glass">
        <form onSubmit={handleConnect}>
          <div className="connect-section-label">
            {TOOL_LABELS[tool]} Credentials
          </div>
          <div className="connect-grid">
            {fields.map(f => (
              <div key={f.key} className="connect-field">
                <label className="connect-label">{f.label}</label>
                <input
                  className="connect-input"
                  type={f.secret ? 'password' : 'text'}
                  placeholder={f.placeholder}
                  value={creds[f.key] || ''}
                  onChange={e => handleCred(f.key, e.target.value)}
                />
              </div>
            ))}
          </div>

          {tool === 'custom' && (
            <p className="connect-note">
              Custom webhook pipelines cannot be auto-discovered.
              Use the <strong>Register Pipeline</strong> tab to add them manually.
            </p>
          )}

          <div className="connect-section-label" style={{ marginTop: 20 }}>
            Optional — Schema Diff &amp; Notifications
          </div>
          <div className="connect-grid">
            <div className="connect-field connect-field-full">
              <label className="connect-label">Source DB Connection String</label>
              <input
                className="connect-input connect-input-mono"
                type="text"
                placeholder="mssql+pyodbc://... (enables schema diff analysis)"
                value={sourceConn}
                onChange={e => setSourceConn(e.target.value)}
              />
            </div>
            <div className="connect-field connect-field-full">
              <label className="connect-label">Target DB Connection String</label>
              <input
                className="connect-input connect-input-mono"
                type="text"
                placeholder="mssql+pyodbc://..."
                value={targetConn}
                onChange={e => setTargetConn(e.target.value)}
              />
            </div>
            <div className="connect-field">
              <label className="connect-label">Notify Email</label>
              <input
                className="connect-input"
                type="email"
                placeholder="oncall@company.com"
                value={notifyEmail}
                onChange={e => setNotifyEmail(e.target.value)}
              />
            </div>
          </div>

          <div className="connect-actions">
            <button
              type="submit"
              className="connect-btn"
              disabled={connecting || tool === 'custom'}
            >
              {connecting ? (
                <><span className="connect-spinner" /> Discovering pipelines…</>
              ) : (
                <>🔍 Connect &amp; Discover Pipelines</>
              )}
            </button>
          </div>

          {/* Result */}
          {result && result.ok && (
            <div className="connect-result success">
              <div className="connect-result-title">
                ✓ Connected to {TOOL_LABELS[tool]}
              </div>
              <div className="connect-result-stats">
                <span className="connect-stat">
                  <span className="connect-stat-num">{result.data.pipelines_discovered}</span>
                  discovered
                </span>
                <span className="connect-stat">
                  <span className="connect-stat-num">{result.data.pipelines_registered}</span>
                  registered
                </span>
                {result.data.pipelines_skipped > 0 && (
                  <span className="connect-stat">
                    <span className="connect-stat-num">{result.data.pipelines_skipped}</span>
                    already registered
                  </span>
                )}
              </div>
              <button
                type="button"
                className="connect-dashboard-btn"
                onClick={() => onConnected && onConnected(result.data.pipelines)}
              >
                → Go to Dashboard
              </button>
            </div>
          )}

          {result && !result.ok && (
            <div className="connect-result error">
              ✗ {result.message}
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
