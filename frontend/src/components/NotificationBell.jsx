import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getNotifications, markRead } from '../api'
import useWebSocket from '../hooks/useWebSocket'

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [notifs, setNotifs] = useState([])
  const navigate = useNavigate()
  const { lastMessage } = useWebSocket('/ws/notifications')

  const load = () => getNotifications().then(setNotifs).catch(() => {})

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (lastMessage?.type === 'notification') load()
  }, [lastMessage])

  const unread = notifs.length

  const handleClick = (n) => {
    markRead(n.id).catch(() => {})
    setNotifs(prev => prev.filter(x => x.id !== n.id))
    setOpen(false)
    navigate(`/incidents/${n.incident_id}`)
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="relative p-2 rounded-full hover:bg-gray-700 transition"
        aria-label="Notifications"
      >
        <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unread > 0 && (
          <span className="absolute top-0 right-0 inline-flex items-center justify-center w-5 h-5 text-xs font-bold text-white bg-red-500 rounded-full">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-96 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50">
          <div className="p-3 border-b border-gray-700 font-semibold text-sm text-gray-200">
            Notifications {unread > 0 && <span className="text-red-400">({unread} unread)</span>}
          </div>
          {notifs.length === 0 ? (
            <p className="p-4 text-sm text-gray-400">No unread notifications.</p>
          ) : (
            <ul className="max-h-80 overflow-y-auto divide-y divide-gray-700">
              {notifs.map(n => (
                <li
                  key={n.id}
                  className="p-3 hover:bg-gray-700 cursor-pointer text-sm text-gray-200"
                  onClick={() => handleClick(n)}
                >
                  <p>{n.message}</p>
                  <p className="text-xs text-gray-500 mt-1">{new Date(n.created_at).toLocaleString()}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
