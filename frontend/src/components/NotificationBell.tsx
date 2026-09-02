import { useEffect, useRef, useState } from 'react'
import apiClient from '../api/client'

interface NotificationItem {
  id: string
  type: string
  message: string
  related_entity_type: string | null
  related_entity_id: string | null
  is_read: boolean
  created_at: string
}

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<NotificationItem[]>([])
  const [unread, setUnread] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  async function loadUnreadCount() {
    try {
      const res = await apiClient.get('/notifications/unread-count')
      setUnread(res.data.unread_count)
    } catch {
      // fail silently - notifications are a non-critical enhancement
    }
  }

  async function loadNotifications() {
    const res = await apiClient.get('/notifications')
    setItems(res.data)
  }

  useEffect(() => {
    loadUnreadCount()
    const interval = setInterval(loadUnreadCount, 20000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  async function toggleOpen() {
    const next = !open
    setOpen(next)
    if (next) {
      await loadNotifications()
    }
  }

  async function markRead(id: string) {
    await apiClient.patch(`/notifications/${id}/read`)
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)))
    loadUnreadCount()
  }

  async function markAllRead() {
    await apiClient.patch('/notifications/mark-all-read')
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })))
    setUnread(0)
  }

  return (
    <div className="notification-bell" ref={containerRef}>
      <button className="bell-trigger" onClick={toggleOpen} aria-label="Notifications">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" fill="currentColor"/>
        </svg>
        {unread > 0 && <span className="bell-badge">{unread > 9 ? '9+' : unread}</span>}
      </button>

      {open && (
        <div className="notification-panel">
          <div className="notification-panel-header">
            <span>Notifications</span>
            {items.some((n) => !n.is_read) && (
              <button className="link-button" onClick={markAllRead}>Mark all as read</button>
            )}
          </div>
          <div className="notification-list">
            {items.length === 0 && <div className="notification-empty">You're all caught up.</div>}
            {items.map((n) => (
              <div
                key={n.id}
                className={`notification-item ${n.is_read ? '' : 'unread'}`}
                onClick={() => !n.is_read && markRead(n.id)}
              >
                <span className="notification-dot" />
                <div>
                  <p>{n.message}</p>
                  <span className="notification-time">{timeAgo(n.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
