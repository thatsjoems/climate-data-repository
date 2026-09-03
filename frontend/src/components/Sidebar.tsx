import { ReactNode, useState } from 'react'

export interface SidebarLink {
  key: string
  label: string
  icon: string
  badgeCount?: number
}

export interface SidebarSection {
  label?: string
  links: SidebarLink[]
}

interface SidebarProps {
  theme: 'navy' | 'light'
  activeKey: string
  onNavigate: (key: string) => void
  sections: SidebarSection[]
  footer?: ReactNode
}

export default function Sidebar({ theme, activeKey, onNavigate, sections, footer }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <aside className={`sidebar theme-${theme} ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">CDR</div>
        {!collapsed && (
          <div className="sidebar-brand-text">
            <strong>Climate Data Repository</strong>
            <span>Bank of Tanzania</span>
          </div>
        )}
      </div>

      <nav className="sidebar-nav">
        {sections.map((section, idx) => (
          <div key={idx}>
            {section.label && !collapsed && <div className="sidebar-section-label">{section.label}</div>}
            {section.links.map((link) => (
              <button
                key={link.key}
                className={`sidebar-link ${activeKey === link.key ? 'active' : ''}`}
                onClick={() => onNavigate(link.key)}
                title={collapsed ? link.label : undefined}
              >
                <span className="icon">{link.icon}</span>
                {!collapsed && <span>{link.label}</span>}
                {!collapsed && link.badgeCount ? <span className="badge-count">{link.badgeCount}</span> : null}
              </button>
            ))}
          </div>
        ))}
      </nav>

      {!collapsed && footer && <div className="sidebar-footer">{footer}</div>}

      <div className="sidebar-footer">
        <button className="sidebar-toggle" onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? '»' : '« Collapse'}
        </button>
      </div>
    </aside>
  )
}
