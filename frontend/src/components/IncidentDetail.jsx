import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getIncident, deleteIncident } from '../api'
import useWebSocket from '../hooks/useWebSocket'
import AgentLog from './AgentLog'
import HILPanel from './HILPanel'

const DRY_RUN_STYLE = {
  PASS: 'bg-green-900 text-green-200 border-green-700',
  FAIL: 'bg-red-900 text-red-200 border-red-700',
}

export default function IncidentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [incident, setIncident] = useState(null)
  const [error, setError] = useState('')

  const load = () => getIncident(id).then(setIncident).catch(e => setError(e.message))

  const handleDelete = async () => {
    if (!window.confirm('Delete this incident? This cannot be undone.')) return
    await deleteIncident(id)
    navigate('/incidents')
  }

  useEffect(() => { load() }, [id])

  const { lastMessage } = useWebSocket(`/ws/incidents/${id}`)

  useEffect(() => {
    if (!lastMessage) return
    if (lastMessage.type === 'incident_update' && lastMessage.incident_id === id) {
      setIncident(prev => {
        if (!prev) return prev
        const updated = { ...prev, status: lastMessage.status }
        if (lastMessage.log_entry) {
          updated.agent_log = [...(prev.agent_log || []), lastMessage.log_entry]
        }
        return updated
      })
    }
  }, [lastMessage, id])

  if (error) return <div className="p-6 text-red-400">{error}</div>
  if (!incident) return <div className="p-6 text-gray-400">Loading…</div>

  const confidence = incident.rca_confidence ?? null

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <span className="text-2xl font-bold text-white">{incident.pipeline_name || 'Unknown Pipeline'}</span>
          <button
            onClick={handleDelete}
            className="ml-auto text-red-500 border border-red-500 hover:bg-red-500 hover:text-white px-3 py-1 rounded text-sm transition-colors"
          >
            🗑 Delete Incident
          </button>
          {incident.priority && (
            <span className="px-2 py-0.5 rounded text-xs font-bold bg-orange-600 text-white">{incident.priority}</span>
          )}
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span>{incident.client_name}</span>
          <span>·</span>
          <span className="font-medium text-blue-400">{incident.status}</span>
          {incident.platform_hint && <><span>·</span><span>{incident.platform_hint}</span></>}
        </div>
        {incident.summary && <p className="mt-2 text-gray-300">{incident.summary}</p>}
      </div>

      {/* Error Info */}
      {incident.error_message && (
        <div className="bg-red-950 border border-red-800 rounded-lg p-4">
          <p className="text-xs font-bold text-red-400 mb-1">ERROR {incident.error_code && `· ${incident.error_code}`}</p>
          <p className="text-red-200 text-sm font-mono whitespace-pre-wrap">{incident.error_message}</p>
        </div>
      )}

      {/* RCA */}
      {incident.rca_hypothesis && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 space-y-3">
          <h2 className="font-semibold text-white">Root Cause Analysis</h2>
          <p className="text-gray-300 text-sm">{incident.rca_hypothesis}</p>

          {confidence !== null && (
            <div>
              <div className="flex justify-between text-xs text-gray-400 mb-1">
                <span>Confidence</span>
                <span className={confidence < 0.6 ? 'text-red-400' : 'text-green-400'}>
                  {(confidence * 100).toFixed(0)}%
                  {confidence < 0.6 && ' — LOW CONFIDENCE'}
                </span>
              </div>
              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${confidence < 0.6 ? 'bg-red-500' : 'bg-green-500'}`}
                  style={{ width: `${(confidence * 100).toFixed(0)}%` }}
                />
              </div>
            </div>
          )}

          {incident.rca_error_category && (
            <span className="inline-block px-2 py-0.5 bg-gray-700 text-gray-300 rounded text-xs">
              {incident.rca_error_category}
            </span>
          )}

          {(incident.rca_evidence || []).length > 0 && (
            <div>
              <p className="text-xs text-gray-400 font-medium mb-1">Evidence</p>
              <ul className="list-disc list-inside text-sm text-gray-300 space-y-0.5">
                {incident.rca_evidence.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Playbook */}
      {incident.fix_strategy && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold text-white">Proposed Fix</h2>
            <span className="px-2 py-0.5 bg-blue-800 text-blue-200 rounded text-xs">{incident.fix_strategy}</span>
          </div>

          {(incident.fix_steps || []).length > 0 && (
            <ol className="list-decimal list-inside text-sm text-gray-300 space-y-1">
              {incident.fix_steps.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          )}

          {incident.fix_instructions && (
            <pre className="text-xs text-gray-400 bg-gray-900 rounded p-3 whitespace-pre-wrap overflow-auto">
              {incident.fix_instructions}
            </pre>
          )}

          {incident.dry_run_result && (
            <div className={`p-3 rounded border text-sm ${DRY_RUN_STYLE[incident.dry_run_result] || 'border-gray-700 text-gray-300'}`}>
              <span className="font-bold">Dry Run: {incident.dry_run_result}</span>
              {incident.dry_run_reasoning && <p className="mt-1 text-xs">{incident.dry_run_reasoning}</p>}
            </div>
          )}
        </div>
      )}

      {/* HIL Panel */}
      <HILPanel incident={incident} onDecision={load} />

      {/* Agent Log */}
      <AgentLog incident={incident} />
    </div>
  )
}
