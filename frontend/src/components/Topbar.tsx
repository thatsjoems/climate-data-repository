import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import NotificationBell from './NotificationBell'

const ROLE_LABELS: Record<string, string> = {
  SYSTEM_ADMIN: 'System Admin',
  BOT_USER: 'BOT Analyst',
  INSTITUTION_USER: 'Institution User',
}

export default function Topbar({ title, crumb }: { title: string; crumb?: string }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  if (!user) return null

  function handleLogout() {
    logout()
    navigate('/login')
  }

  const initials = user.full_name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div>
          <div className="topbar-title">{title}</div>
          {crumb && <div className="topbar-crumb">{crumb}</div>}
        </div>
      </div>
      <div className="topbar-right">
        <NotificationBell />
        <div className="topbar-user-info">
          <span className="topbar-avatar">{initials}</span>
          <span className="topbar-user-text">
            <strong>{user.full_name}</strong>
            <em>{ROLE_LABELS[user.role] || user.role}</em>
          </span>
        </div>
        <button className="logout-button" onClick={handleLogout}>Log Out</button>
      </div>
    </header>
  )
}
