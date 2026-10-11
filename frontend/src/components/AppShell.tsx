import type { ReactNode } from 'react'
import type { AppRoute } from '../types'

const navigation: Array<{ route: AppRoute; label: string; mark: string }> = [
  { route: '/home', label: 'Home', mark: 'H' },
  { route: '/chat', label: 'Chat', mark: 'C' },
  { route: '/images', label: 'Images', mark: 'I' },
  { route: '/video', label: 'Video Editing', mark: 'V' },
  { route: '/uploads', label: 'Uploads', mark: 'U' },
  { route: '/profile', label: 'Settings', mark: 'S' },
]

type AppShellProps = {
  activeRoute: AppRoute
  onNavigate: (route: AppRoute) => void
  children: ReactNode
}

export function AppShell({ activeRoute, onNavigate, children }: AppShellProps) {
  return (
    <div className="app-frame">
      <aside className="sidebar" aria-label="Main navigation">
        <button className="brand" type="button" onClick={() => onNavigate('/home')}>
          <span className="brand-mark">S</span>
          <span><strong>ShortsFlow</strong><small>AI studio</small></span>
        </button>
        <nav className="nav-list">
          {navigation.map((item) => {
            const isActive = activeRoute === item.route || (activeRoute === '/' && item.route === '/home')
            return <button
              className={`nav-item ${isActive ? 'active' : ''}`}
              aria-current={isActive ? 'page' : undefined}
              type="button"
              key={item.route}
              onClick={() => onNavigate(item.route)}
            >
              <span className="nav-mark">{item.mark}</span>{item.label}
            </button>
          })}
        </nav>
        <div className="sidebar-footer"><span className="status-dot" /> Workspace ready</div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  )
}
