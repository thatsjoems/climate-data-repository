import { useState, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import NotificationBell from './NotificationBell'
import botLogo from '../assets/bot_logo.png'
import coatOfArms from '../assets/tanzania_coat_of_arms.jpg'

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
  // Off-canvas menu, matching the pattern on bot.go.tz: hidden by default
  // (not a persistent, always-visible sidebar) - the hamburger in the
  // navbar below slides it in as an overlay on top of the content, with a
  // dark backdrop behind it; the backdrop, the "x" inside the menu, or
  // choosing a navigation item all close it again, also like the real site.
  const [menuOpen, setMenuOpen] = useState(false)

  function handleLogout() {
    logout()
    navigate('/login')
  }

  function handleNavItemClick(onClick: () => void) {
    onClick()
    setMenuOpen(false)
  }

  return (
    <div className={`portal-shell theme-${theme}`}>
      {menuOpen && <div className="sidebar-backdrop" onClick={() => setMenuOpen(false)} />}

      <aside className={`portal-sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="sidebar-close-row">
          <img src={botLogo} alt="Bank of Tanzania" className="sidebar-bot-logo" />
          <button className="sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close menu">&times;</button>
        </div>
        <nav className="sidebar-nav">
          <div className="sidebar-section-label">Navigation</div>
          {items.map((item) => (
            <button
              key={item.key}
              className={`sidebar-item ${item.active ? 'active' : ''}`}
              onClick={() => handleNavItemClick(item.onClick)}
              title={item.label}
            >
              <span className="sidebar-icon">{item.icon}</span>
              <span className="sidebar-label">{item.label}</span>
            </button>
          ))}
          <button className="sidebar-item" onClick={() => handleNavItemClick(() => navigate('/change-password'))} title="Change Password">
            <span className="sidebar-icon">🔒</span>
            <span className="sidebar-label">Change Password</span>
          </button>
          <button className="sidebar-item" onClick={() => handleNavItemClick(handleLogout)} title="Log Out">
            <span className="sidebar-icon">🚪</span>
            <span className="sidebar-label">Log Out</span>
          </button>
        </nav>

        {platforms && platforms.length > 0 && (
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
        {/*
          Two-tier header per the supplied design spec.
          Tier 1 (.top-header): gold gradient, Coat of Arms (left) / title
          (center) / BOT emblem (right), 3px dark-gold bottom border.
          tanzania_coat_of_arms.jpg (user-supplied) is the real national
          Coat of Arms - shown as a round white "medallion" badge
          (.coat-of-arms-badge) since the source file itself has a plain
          white background. Its use here is official/internal (a Bank of
          Tanzania system), which is squarely the kind of use Tanzania's
          National Emblems Act (Cap. 10) is written to allow - unlike the
          Act's actual target (commercial/trade or unauthorised personal
          use) - but confirm with BOT's own compliance process if this
          goes into a public-facing deployment, since that Act still
          requires the Home Affairs Minister's authorisation for use
          outside government itself.
          Tier 2 (.navbar): dark bar, hamburger (left, opens the off-canvas
          menu - see the slide-in pattern on bot.go.tz, requested as the
          model: hidden by default, overlays the content when opened rather
          than sitting in the layout permanently) and the signed-in user's
          role (right). The
          page title/subtitle and the notification bell were already part
          of this shell before this redesign and aren't in the supplied
          spec; rather than drop them, they're placed here too (title next
          to the hamburger, bell just before the role text) so nothing that
          worked before is silently lost - remove either if not wanted.
        */}
        <header className="top-header">
          <span className="coat-of-arms-badge">
            <img src={coatOfArms} alt="Coat of Arms of the United Republic of Tanzania" className="coat-of-arms-img" />
          </span>
          <h1 className="top-header-title">Bank of Tanzania</h1>
          <img src={botLogo} alt="Bank of Tanzania" className="top-header-bot-logo" />
        </header>

        <nav className="navbar">
          <div className="navbar-left">
            <button className="hamburger-menu" onClick={() => setMenuOpen(!menuOpen)} aria-label="Open menu">
              &#9776;
            </button>
            <div className="navbar-page-title">
              <span>{pageTitle}</span>
              {pageSubtitle && <em>{pageSubtitle}</em>}
            </div>
          </div>
          <div className="navbar-right">
            <NotificationBell />
            <span className="user-role">
              {user?.role === 'INSTITUTION_USER' ? 'Institution User' : user?.role === 'BOT_USER' ? 'BOT Analyst (internal)' : 'System Admin'}
            </span>
          </div>
        </nav>

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
