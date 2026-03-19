import { useState } from 'react'
import { submitHILDecision } from '../api'

export default function HILPanel({ incident, onDecision }) {
  const [email, setEmail]     = useState('')
  const [loading, setLoading] = useState(null)
  const [error, setError]     = useState('')

  const canDecide = incident?.status === 'AWAITING_HIL'

  const submit = async (decision) => {
    if (!email.trim()) { setError('Engineer email is required'); return }
    setLoading(decision)
    setError('')
    try {
      await submitHILDecision(incident.id, decision, email)
      onDecision?.(decision)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className={`p-4 rounded-lg border ${canDecide ? 'border-yellow-600 bg-yellow-950' : 'border-gray-700 bg-gray-800'}`}>
      <h3 className="font-semibold text-white mb-3">Human Approval Required</h3>

      {!canDecide && (
        <p className="text-sm text-gray-400">
          {incident?.decision === 'approve'
            ? 'Fix was approved.'
            : incident?.decision === 'reject'
            ? 'Fix was rejected.'
            : `Approval not available — current status: ${incident?.status}`}
        </p>
      )}

      {canDecide && (
        <>
          <p className="text-sm text-yellow-200 mb-4">
            Review the proposed fix above. No changes will be made until you approve.
          </p>
          <div className="mb-4">
            <label className="block text-xs text-gray-400 mb-1">Your email</label>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="engineer@company.com"
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
            />
          </div>
          {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
          <div className="flex gap-3">
            <button
              onClick={() => submit('approve')}
              disabled={!!loading}
              className="flex-1 bg-green-600 hover:bg-green-700 text-white py-2 rounded font-medium text-sm disabled:opacity-50"
            >
              {loading === 'approve' ? 'Approving…' : 'Approve Fix'}
            </button>
            <button
              onClick={() => submit('reject')}
              disabled={!!loading}
              className="flex-1 bg-red-700 hover:bg-red-800 text-white py-2 rounded font-medium text-sm disabled:opacity-50"
            >
              {loading === 'reject' ? 'Rejecting…' : 'Reject Fix'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
