import { useState, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import NotificationBell from './NotificationBell'

export interface SidebarItem {
  key: string
  icon: string
  label: string
  onClick: () => void
  active?: boolean
}

export interface PlatformStatus {
  name: string
  connected: boolean
}

interface PortalShellProps {
  theme: 'institution' | 'bot'
  brandTitle: string
  brandSubtitle: string
  pageTitle: string
  pageSubtitle?: string
  items: SidebarItem[]
  platforms?: PlatformStatus[]
  children: ReactNode
}

export default function PortalShell({
  theme, brandTitle, brandSubtitle, pageTitle, pageSubtitle, items, platforms, children,
}: PortalShellProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  function handleLogout() {
    logout()
    navigate('/login')
  }

  const emblemText = theme === 'institution' ? 'CDR' : 'BOT'

  return (
    <div className={`portal-shell theme-${theme}`}>
      <aside className={`portal-sidebar ${collapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-brand">
          <div className="sidebar-brand-emblem">{emblemText}</div>
          {!collapsed && (
            <div className="sidebar-brand-text">
              <strong>{brandTitle}</strong>
              <span>{brandSubtitle}</span>
            </div>
          )}
          <button className="sidebar-toggle" onClick={() => setCollapsed(!collapsed)} aria-label="Toggle sidebar">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>
          </button>
        </div>

        <nav className="sidebar-nav">
          {!collapsed && <div className="sidebar-section-label">Navigation</div>}
          {items.map((item) => (
            <button
              key={item.key}
              className={`sidebar-item ${item.active ? 'active' : ''}`}
              onClick={item.onClick}
              title={item.label}
            >
              <span className="sidebar-icon">{item.icon}</span>
              {!collapsed && <span className="sidebar-label">{item.label}</span>}
            </button>
          ))}
          <button className="sidebar-item" onClick={handleLogout} title="Log Out">
            <span className="sidebar-icon">🚪</span>
            {!collapsed && <span className="sidebar-label">Log Out</span>}
          </button>
        </nav>

        {platforms && platforms.length > 0 && !collapsed && (
          <div className="sidebar-platform-list">
            <div className="sidebar-section-label" style={{ padding: '0 0 0.4rem' }}>Integrated Platforms</div>
            {platforms.map((p) => (
              <div className="platform-row" key={p.name}>
                <span>{p.name}</span>
                <span
                  className="platform-status"
                  style={{
                    background: p.connected ? '#E6F6EE' : '#F1F0EC',
                    color: p.connected ? '#0B7D62' : '#8A8677',
                  }}
                >
                  {p.connected ? 'Connected' : 'Not Connected'}
                </span>
              </div>
            ))}
          </div>
        )}
      </aside>

      <div className="portal-main">
        <header className="portal-topbar">
          <div className="portal-topbar-title">
            <h1>{pageTitle}</h1>
            {pageSubtitle && <span>{pageSubtitle}</span>}
          </div>
          <div className="portal-topbar-right">
            <NotificationBell />
            <div className="navbar-user-info">
              <span className="navbar-avatar" style={{ color: 'var(--color-text)', background: 'rgba(0,0,0,0.06)', border: '1px solid var(--color-border)' }}>
                {user?.full_name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()}
              </span>
              <span className="navbar-user-text" style={{ color: 'inherit' }}>
                <strong>{user?.full_name}</strong>
                <em>{user?.role === 'INSTITUTION_USER' ? 'Institution User' : user?.role === 'BOT_USER' ? 'BOT Analyst' : 'System Admin'}</em>
              </span>
            </div>
          </div>
        </header>

        <main className="portal-content">{children}</main>

        <footer className="portal-footer">
          <span>🎧 Need Support? We are here to help.</span>
          <span>✉️ cdr-support@bot.go.tz</span>
          <span>📞 +255 22 223 5963</span>
        </footer>
      </div>
    </div>
  )
}
