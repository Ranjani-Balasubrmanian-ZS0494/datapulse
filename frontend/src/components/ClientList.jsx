import { useState, useEffect } from 'react'
import { getClients, createClient, deleteClient } from '../api'

const INDUSTRIES = ['NBFC', 'NGO', 'ecommerce', 'other']

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).catch(() => {})
}

export default function ClientList() {
  const [clients, setClients] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ name: '', industry: 'NBFC' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(null)

  const load = () => getClients().then(setClients).catch(e => setError(e.message))

  useEffect(() => { load() }, [])

  const handleCreate = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await createClient(form)
      setShowModal(false)
      setForm({ name: '', industry: 'NBFC' })
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this client and all their incidents?')) return
    await deleteClient(id).catch(e => setError(e.message))
    load()
  }

  const handleCopy = (id, text) => {
    copyToClipboard(text)
    setCopied(id)
    setTimeout(() => setCopied(null), 2000)
  }

  const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Clients</h1>
        <button
          onClick={() => setShowModal(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          + Add Client
        </button>
      </div>

      {error && <div className="mb-4 p-3 bg-red-900 text-red-200 rounded">{error}</div>}

      {/* Onboarding checklist */}
      <div className="mb-6 p-4 bg-gray-800 rounded-lg border border-gray-700">
        <h2 className="font-semibold text-gray-200 mb-2">How to onboard a new client</h2>
        <ol className="list-decimal list-inside text-sm text-gray-400 space-y-1">
          <li>Add the client above and copy their webhook URL.</li>
          <li>Paste the webhook URL into their pipeline tool failure alert setting.</li>
          <li>Set the Authorization header to <code className="bg-gray-700 px-1 rounded">Bearer &lt;webhook_secret&gt;</code>.</li>
          <li>Trigger a test failure — you should see an incident appear within seconds.</li>
          <li>Done — the client is connected.</li>
        </ol>
      </div>

      {clients.length === 0 ? (
        <p className="text-gray-400">No clients yet. Add your first client above.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-gray-400 uppercase bg-gray-800">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Industry</th>
                <th className="px-4 py-3">Webhook URL</th>
                <th className="px-4 py-3">Secret</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {clients.map(c => {
                const webhookUrl = `${BASE}/ingest/${c.id}`
                return (
                  <tr key={c.id} className="bg-gray-900 hover:bg-gray-800 text-gray-200">
                    <td className="px-4 py-3 font-medium">{c.name}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 bg-blue-900 text-blue-200 rounded text-xs">{c.industry}</span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-400 max-w-xs truncate">
                      {webhookUrl}
                      <button
                        onClick={() => handleCopy(c.id + '-url', webhookUrl)}
                        className="ml-2 text-blue-400 hover:text-blue-300"
                      >
                        {copied === c.id + '-url' ? '✓' : 'Copy'}
                      </button>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">
                      {c.webhook_secret.slice(0, 8)}…
                      <button
                        onClick={() => handleCopy(c.id + '-sec', c.webhook_secret)}
                        className="ml-2 text-blue-400 hover:text-blue-300"
                      >
                        {copied === c.id + '-sec' ? '✓' : 'Copy'}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleDelete(c.id)}
                        className="text-red-400 hover:text-red-300 text-xs"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Add Client Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h2 className="text-lg font-bold text-white mb-4">Add New Client</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Client Name</label>
                <input
                  required
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                  placeholder="Acme Corp"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Industry</label>
                <select
                  value={form.industry}
                  onChange={e => setForm(f => ({ ...f, industry: e.target.value }))}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm"
                >
                  {INDUSTRIES.map(i => <option key={i}>{i}</option>)}
                </select>
              </div>
              {error && <p className="text-red-400 text-sm">{error}</p>}
              <div className="flex gap-3 justify-end">
                <button type="button" onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
                <button type="submit" disabled={loading}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded disabled:opacity-50">
                  {loading ? 'Creating…' : 'Create Client'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
