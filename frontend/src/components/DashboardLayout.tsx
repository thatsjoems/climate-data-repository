import { ReactNode } from 'react'
import Sidebar, { SidebarSection } from './Sidebar'
import Topbar from './Topbar'

interface DashboardLayoutProps {
  theme: 'navy' | 'light'
  sections: SidebarSection[]
  activeKey: string
  onNavigate: (key: string) => void
  title: string
  crumb?: string
  sidebarFooter?: ReactNode
  children: ReactNode
}

export default function DashboardLayout({
  theme, sections, activeKey, onNavigate, title, crumb, sidebarFooter, children,
}: DashboardLayoutProps) {
  return (
    <div className="dashboard-shell">
      <Sidebar theme={theme} activeKey={activeKey} onNavigate={onNavigate} sections={sections} footer={sidebarFooter} />
      <div className="main-area">
        <Topbar title={title} crumb={crumb} />
        {children}
      </div>
    </div>
  )
}
