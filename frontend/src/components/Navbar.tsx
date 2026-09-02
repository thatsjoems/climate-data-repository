import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import NotificationBell from './NotificationBell'

const ROLE_LABELS: Record<string, string> = {
  SYSTEM_ADMIN: 'System Admin',
  BOT_USER: 'BOT Analyst',
  INSTITUTION_USER: 'Institution User',
}

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  if (!user) return null

  function handleLogout() {
    logout()
    navigate('/login')
  }

  const initials = user.full_name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <div className="navbar-logo">CDR</div>
        <div>
          <span className="navbar-title">Climate Data Repository</span>
          <span className="navbar-subtitle">Bank of Tanzania</span>
        </div>
      </div>
      <div className="navbar-links">
        {user.role === 'INSTITUTION_USER' && <Link to="/">My Dashboard</Link>}
        {(user.role === 'BOT_USER' || user.role === 'SYSTEM_ADMIN') && <Link to="/">Internal Dashboard</Link>}
        {user.role === 'SYSTEM_ADMIN' && <Link to="/admin">Administration</Link>}
      </div>
      <div className="navbar-user">
        <NotificationBell />
        <div className="navbar-user-info">
          <span className="navbar-avatar">{initials}</span>
          <span className="navbar-user-text">
            <strong>{user.full_name}</strong>
            <em>{ROLE_LABELS[user.role] || user.role}</em>
          </span>
        </div>
        <button className="logout-button" onClick={handleLogout}>Log Out</button>
      </div>
    </nav>
  )
}
