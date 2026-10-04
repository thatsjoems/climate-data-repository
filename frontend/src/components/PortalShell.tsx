import { useRef, useState, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import NotificationBell from './NotificationBell'
import botLogo from '../assets/bot_logo.png'
import botLogoSquarePale from '../assets/bot_logo_square_pale.png'
import coatOfArms from '../assets/tanzania_coat_of_arms.png'

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
  // The "Menu" tab of the left-edge opener below; moved straight in the DOM (not through
  // state) so following the cursor does not re-render the page on every mouse move.
  const edgeTabRef = useRef<HTMLDivElement>(null)

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
      {/*
        Left-edge menu opener, for mouse users. The hamburger sits in the page's top strip
        and scrolls out of view, so this thin fixed zone on the viewport's left edge lets the
        menu be opened from anywhere: hovering it reveals a "Menu" tab at the cursor's height,
        and a click opens the sidebar - which is position: fixed, so it appears wherever the
        page is scrolled to. Rendered only while the menu is closed. aria-hidden on purpose:
        it is a pointer convenience; the hamburger remains the accessible control.
      */}
      {!menuOpen && (
        <div
          className="nav-edge-trigger"
          aria-hidden="true"
          onClick={() => setMenuOpen(true)}
          onMouseMove={(e) => {
            if (e.target === e.currentTarget && edgeTabRef.current) {
              const y = Math.min(Math.max(e.clientY, 32), window.innerHeight - 32)
              edgeTabRef.current.style.top = `${y}px`
            }
          }}
        >
          <div className="nav-edge-tab" ref={edgeTabRef}>
            <span>&#9776;</span>
            <span>Menu</span>
          </div>
        </div>
      )}

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
          Two-strip header, following the supplied spec.
          Top strip (.top-header): gold gradient (.strip-background:
          #E8E3CE -> #D9BD59 -> #EAE8E3), Coat of Arms (left), "BANK OF
          TANZANIA" (centre), BOT emblem (right), and a 4px bottom line in the
          Tanzanian flag's green, black and blue (.strip-bottom-border). Bottom strip
          (.navbar): #1A1A1A, starting with a 24x24 white hamburger in a
          thin dotted box, left-aligned with the Coat of Arms above.
          Strip heights, emblem sizes and the title size are fixed values
          that started from measurements of the BOT site and were then
          reduced on request - see the comment above --header-top-h in
          index.css for the current numbers (banner 94.5px / strip 45px on
          desktop, 68.4px / 50px at <= 768px; Coat of Arms 68.85x81px, BOT
          emblem 85.5x85.5px; 40.5x48.6px and 49.5x49.5px on phones).

          Assets: tanzania_coat_of_arms.png is the user-supplied national
          Coat of Arms with its white JPG background removed (a border-
          connected flood fill plus removal of the large enclosed gaps
          between the tusks and shield; the ivory tusks, the shield's wave
          pattern and the motto ribbon are untouched). bot_logo_square.png
          is bot_logo.png trimmed of its transparent margins and padded to
          an exact square, so the emblem fills its 1:1 box - the original
          235x115 file is mostly empty space and rendered tiny in a square.
          bot_logo_square_pale.png (used here) is that same file tinted 45%
          toward a pale gold on request, as the original amber looked too
          deep; bot_logo_square.png is kept so the full colour can be
          restored by changing one import. The unmodified bot_logo.png is
          still used by the sidebar and login page.

          Legal note, as before: the Coat of Arms' use here is official/
          internal (a Bank of Tanzania system), which is the kind of use
          Tanzania's National Emblems Act (Cap. 10) is not aimed at, but
          that is not legal advice - confirm with BOT's compliance process,
          especially before any public-facing deployment.

          On request, the dark strip also carries the page title/subtitle
          (right after the hamburger - on the BOT Analyst portal that is
          "Climate Data Repository" and its tagline) and, on its right, the
          notification bell and the signed-in user's role. This supersedes the
          earlier hamburger-only spec, and the interim arrangement that had
          moved these into the content area.
        */}
        <header className="top-header strip-background strip-bottom-border">
          <img src={coatOfArms} alt="Coat of Arms of the United Republic of Tanzania" className="top-header-coat" />
          <h1 className="top-header-title">Bank of Tanzania</h1>
          <img src={botLogoSquarePale} alt="Bank of Tanzania" className="top-header-bot-logo" />
        </header>

        <nav className="navbar">
          <div className="navbar-left">
            <button className="hamburger-menu" onClick={() => setMenuOpen(!menuOpen)} aria-label="Open menu">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M3 6h18M3 12h18M3 18h18" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
              </svg>
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
