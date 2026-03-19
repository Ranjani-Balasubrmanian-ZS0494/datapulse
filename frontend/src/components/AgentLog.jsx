import { useEffect, useRef } from 'react'

const AGENT_COLORS = {
  SIGNAL_FUSION: 'bg-blue-600',
  RCA:           'bg-purple-600',
  PLAYBOOK:      'bg-orange-600',
  FIX_EXECUTOR:  'bg-green-600',
  HIL:           'bg-yellow-600',
}

const ACTIVE_STATUSES = ['DETECTING', 'RCA_IN_PROGRESS', 'PLAYBOOK_IN_PROGRESS', 'FIXING']

function currentAgent(status) {
  if (status === 'DETECTING')            return 'SIGNAL_FUSION'
  if (status === 'RCA_IN_PROGRESS')      return 'RCA'
  if (status === 'PLAYBOOK_IN_PROGRESS') return 'PLAYBOOK'
  if (status === 'FIXING')               return 'FIX_EXECUTOR'
  return null
}

export default function AgentLog({ incident }) {
  const bottomRef = useRef(null)
  const log = incident?.agent_log || []
  const active = currentAgent(incident?.status)
  const isRunning = ACTIVE_STATUSES.includes(incident?.status)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log.length])

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700">
        <span className="font-semibold text-sm text-gray-200">Agent Log</span>
        {isRunning && (
          <span className="flex items-center gap-1 text-xs text-green-400">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            Running
          </span>
        )}
      </div>

      <div className="max-h-80 overflow-y-auto p-4 space-y-3 font-mono text-xs">
        {log.length === 0 && (
          <p className="text-gray-500">Waiting for agent activity…</p>
        )}
        {log.map((entry, i) => {
          const isActive = entry.agent === active && i === log.length - 1 && isRunning
          const color = AGENT_COLORS[entry.agent] || 'bg-gray-600'
          return (
            <div key={i} className="flex gap-3 items-start">
              <div className="flex-shrink-0 flex items-center gap-1">
                <span className={`px-1.5 py-0.5 rounded text-white text-xs font-bold ${color}`}>
                  {entry.agent}
                </span>
                {isActive && <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />}
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-gray-500">{new Date(entry.timestamp).toLocaleTimeString()} </span>
                <span className="text-yellow-400">[{entry.action}] </span>
                <span className="text-gray-300 break-words">{entry.detail}</span>
              </div>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
