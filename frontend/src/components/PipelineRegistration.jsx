import React, { useState, useEffect } from 'react'
import { registerPipeline, listPipelines, deletePipeline, reportFailure } from '../api.js'

// ---------------------------------------------------------------------------
// Tool credential field definitions
// ---------------------------------------------------------------------------
const TOOL_FIELDS = {
  adf: [
    { key: 'tenant_id',       label: 'Tenant ID',        placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
    { key: 'client_id',       label: 'Client ID',        placeholder: 'Service principal app ID' },
    { key: 'client_secret',   label: 'Client Secret',    placeholder: 'Service principal secret', secret: true },
    { key: 'subscription_id', label: 'Subscription ID',  placeholder: 'Azure subscription ID' },
    { key: 'resource_group',  label: 'Resource Group',   placeholder: 'my-resource-group' },
    { key: 'factory_name',    label: 'Factory Name',     placeholder: 'my-adf-factory' },
    { key: 'pipeline_name',   label: 'Pipeline Name',    placeholder: 'my-pipeline' },
  ],
  databricks: [
    { key: 'host',    label: 'Workspace Host URL', placeholder: 'https://adb-xxxx.azuredatabricks.net' },
    { key: 'token',   label: 'Access Token',       placeholder: 'dapi...', secret: true },
    { key: 'job_id',  label: 'Job ID',             placeholder: '12345' },
  ],
  synapse: [
    { key: 'tenant_id',       label: 'Tenant ID',        placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
    { key: 'client_id',       label: 'Client ID',        placeholder: 'Service principal app ID' },
    { key: 'client_secret',   label: 'Client Secret',    placeholder: 'Service principal secret', secret: true },
    { key: 'subscription_id', label: 'Subscription ID',  placeholder: 'Azure subscription ID' },
    { key: 'resource_group',  label: 'Resource Group',   placeholder: 'my-resource-group' },
    { key: 'workspace_name',  label: 'Workspace Name',   placeholder: 'my-synapse-workspace' },
    { key: 'pipeline_name',   label: 'Pipeline Name',    placeholder: 'my-pipeline' },
  ],
  custom: [
    { key: 'webhook_url', label: 'Webhook URL',           placeholder: 'https://your-system.com/rerun' },
    { key: 'headers',     label: 'Extra Headers (JSON)',  placeholder: '{"Authorization": "Bearer token"}' },
  ],
}

const TOOL_LABELS = {
  adf:        'Azure Data Factory',
  databricks: 'Databricks',
  synapse:    'Azure Synapse',
  custom:     'Custom Webhook',
}

const EMPTY_FORM = {
  name: '',
  tool: 'adf',
  source_db_conn: '',
  target_db_conn: '',
  notify_email: '',
  tool_credentials: {},
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PipelineRegistration() {
  const [form, setForm]           = useState(EMPTY_FORM)
  const [credFields, setCredFields] = useState({})
  const [pipelines, setPipelines] = useState([])
  const [saving, setSaving]       = useState(false)
  const [saveResult, setSaveResult] = useState(null)  // {ok, message}
  const [testPipelineId, setTestPipelineId] = useState('')
  const [testError, setTestError] = useState('Column total_price not found in source database')
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting]     = useState(false)

  // Reload registered pipelines
  const fetchPipelines = async () => {
    try {
      const list = await listPipelines()
      setPipelines(list)
    } catch (_) {}
  }

  useEffect(() => { fetchPipelines() }, [])

  // Reset credential fields when tool changes
  const handleToolChange = (tool) => {
    setForm(f => ({ ...f, tool }))
    setCredFields({})
  }

  const handleCredChange = (key, value) => {
    setCredFields(f => ({ ...f, [key]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) return

    setSaving(true)
    setSaveResult(null)
    try {
      await registerPipeline({
        ...form,
        tool_credentials: credFields,
      })
      setSaveResult({ ok: true, message: `Pipeline "${form.name}" registered successfully.` })
      setForm(EMPTY_FORM)
      setCredFields({})
      await fetchPipelines()
    } catch (err) {
      setSaveResult({ ok: false, message: `Error: ${err.message}` })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Remove pipeline "${name}"?`)) return
    try {
      await deletePipeline(id)
      await fetchPipelines()
    } catch (err) {
      alert(`Failed to delete: ${err.message}`)
    }
  }

  const handleTestFailure = async (e) => {
    e.preventDefault()
    if (!testPipelineId) return
    setTesting(true)
    setTestResult(null)
    try {
      const res = await reportFailure({
        pipeline_id: testPipelineId,
        error_message: testError,
        run_id: '',
      })
      setTestResult({ ok: true, message: `Incident created: ${res.incident_id}. Status: ${res.status}` })
    } catch (err) {
      setTestResult({ ok: false, message: `Error: ${err.message}` })
    } finally {
      setTesting(false)
    }
  }

  const fields = TOOL_FIELDS[form.tool] || []

  return (
    <div className="registration-page">

      {/* ── Register form ─────────────────────────────────────────────── */}
      <div className="reg-section glass">
        <h2 className="reg-title">Register a Pipeline</h2>
        <p className="reg-subtitle">
          Connect any pipeline tool to the self-healing platform. When a failure occurs,
          your monitoring system calls <code>POST /pipeline/failure</code> with the
          pipeline ID and error message — our AI agents handle the rest.
        </p>

        <form onSubmit={handleSubmit} className="reg-form">
          {/* Basic info */}
          <div className="reg-grid">
            <div className="reg-field">
              <label className="reg-label">Pipeline Name *</label>
              <input
                className="reg-input"
                type="text"
                placeholder="e.g. Sales ETL Daily Load"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                required
              />
            </div>

            <div className="reg-field">
              <label className="reg-label">Pipeline Tool *</label>
              <select
                className="reg-input reg-select"
                value={form.tool}
                onChange={e => handleToolChange(e.target.value)}
              >
                {Object.entries(TOOL_LABELS).map(([val, label]) => (
                  <option key={val} value={val}>{label}</option>
                ))}
              </select>
            </div>

            <div className="reg-field">
              <label className="reg-label">Notify Email</label>
              <input
                className="reg-input"
                type="email"
                placeholder="oncall@company.com"
                value={form.notify_email}
                onChange={e => setForm(f => ({ ...f, notify_email: e.target.value }))}
              />
            </div>
          </div>

          {/* Optional DB connections */}
          <div className="reg-section-label">
            Source &amp; Target DB (optional — enables schema diff analysis)
          </div>
          <div className="reg-grid">
            <div className="reg-field reg-field-full">
              <label className="reg-label">Source DB Connection String</label>
              <input
                className="reg-input reg-input-mono"
                type="text"
                placeholder="mssql+pyodbc://..."
                value={form.source_db_conn}
                onChange={e => setForm(f => ({ ...f, source_db_conn: e.target.value }))}
              />
            </div>
            <div className="reg-field reg-field-full">
              <label className="reg-label">Target DB Connection String</label>
              <input
                className="reg-input reg-input-mono"
                type="text"
                placeholder="mssql+pyodbc://..."
                value={form.target_db_conn}
                onChange={e => setForm(f => ({ ...f, target_db_conn: e.target.value }))}
              />
            </div>
          </div>

          {/* Tool-specific credentials */}
          <div className="reg-section-label">
            {TOOL_LABELS[form.tool]} Credentials
          </div>
          <div className="reg-grid">
            {fields.map(f => (
              <div key={f.key} className="reg-field">
                <label className="reg-label">{f.label}</label>
                <input
                  className={`reg-input${f.secret ? ' reg-input-secret' : ''}`}
                  type={f.secret ? 'password' : 'text'}
                  placeholder={f.placeholder}
                  value={credFields[f.key] || ''}
                  onChange={e => handleCredChange(f.key, e.target.value)}
                />
              </div>
            ))}
          </div>

          <div className="reg-actions">
            <button
              type="submit"
              className="approve-btn"
              disabled={saving || !form.name.trim()}
            >
              {saving ? 'Registering…' : '+ Register Pipeline'}
            </button>
          </div>

          {saveResult && (
            <div className={`hil-result ${saveResult.ok ? 'success' : 'error'}`}>
              {saveResult.message}
            </div>
          )}
        </form>
      </div>

      {/* ── Registered Pipelines ──────────────────────────────────────── */}
      <div className="reg-section glass">
        <h2 className="reg-title">Registered Pipelines ({pipelines.length})</h2>

        {pipelines.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
            No pipelines registered yet. Use the form above to add one.
          </p>
        ) : (
          <div className="pipeline-cards">
            {pipelines.map(p => (
              <div key={p.id} className="pipeline-card glass">
                <div className="pipeline-card-header">
                  <div>
                    <div className="pipeline-card-name">{p.name}</div>
                    <div className="pipeline-card-id">{p.id}</div>
                  </div>
                  <div className="pipeline-card-badges">
                    <span className="tool-badge">{TOOL_LABELS[p.tool] || p.tool}</span>
                    <button
                      className="reject-btn"
                      style={{ padding: '4px 10px', fontSize: '11px' }}
                      onClick={() => handleDelete(p.id, p.name)}
                    >
                      Remove
                    </button>
                  </div>
                </div>

                {p.notify_email && (
                  <div className="pipeline-card-detail">
                    <span className="pipeline-card-label">Notify:</span> {p.notify_email}
                  </div>
                )}

                <div className="pipeline-card-detail pipeline-card-endpoint">
                  <span className="pipeline-card-label">Failure endpoint:</span>{' '}
                  <code>POST /pipeline/failure  {`{"pipeline_id": "${p.id}", "error_message": "..."}`}</code>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Simulate Failure (for testing) ───────────────────────────── */}
      {pipelines.length > 0 && (
        <div className="reg-section glass">
          <h2 className="reg-title">Simulate Failure</h2>
          <p className="reg-subtitle">
            Test the AI healing flow without waiting for a real failure.
            This calls <code>POST /pipeline/failure</code> on your behalf.
          </p>

          <form onSubmit={handleTestFailure} className="reg-form">
            <div className="reg-grid">
              <div className="reg-field">
                <label className="reg-label">Pipeline</label>
                <select
                  className="reg-input reg-select"
                  value={testPipelineId}
                  onChange={e => setTestPipelineId(e.target.value)}
                  required
                >
                  <option value="">— select pipeline —</option>
                  {pipelines.map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>

              <div className="reg-field reg-field-full">
                <label className="reg-label">Error Message</label>
                <input
                  className="reg-input"
                  type="text"
                  value={testError}
                  onChange={e => setTestError(e.target.value)}
                />
              </div>
            </div>

            <div className="reg-actions">
              <button
                type="submit"
                className="approve-btn"
                disabled={testing || !testPipelineId}
              >
                {testing ? 'Triggering…' : '⚡ Simulate Failure'}
              </button>
            </div>

            {testResult && (
              <div className={`hil-result ${testResult.ok ? 'success' : 'error'}`}>
                {testResult.message}
              </div>
            )}
          </form>
        </div>
      )}

    </div>
  )
}
