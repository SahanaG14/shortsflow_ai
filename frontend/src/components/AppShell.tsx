import { useState, type ReactNode } from 'react'
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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const isActiveRoute = (route: AppRoute) => activeRoute === route || (activeRoute === '/' && route === '/home')
  const navigate = (route: AppRoute) => {
    onNavigate(route)
    setMobileMenuOpen(false)
  }

  return (
    <div className="app-frame">
      <aside className="sidebar" aria-label="Main navigation">
        <button className="brand" type="button" onClick={() => navigate('/home')}>
          <span className="brand-mark">S</span>
          <span><strong>ShortsFlow</strong><small>AI studio</small></span>
        </button>
        <nav className="nav-list">
          {navigation.map((item) => {
            const isActive = isActiveRoute(item.route)
            return <button
              className={`nav-item ${isActive ? 'active' : ''}`}
              aria-current={isActive ? 'page' : undefined}
              type="button"
              key={item.route}
              onClick={() => navigate(item.route)}
            >
              <span className="nav-mark">{item.mark}</span>{item.label}
            </button>
          })}
        </nav>
        <div className="sidebar-footer"><span className="status-dot" /> Workspace ready</div>
      </aside>
      <header className="mobile-header">
        <button className="mobile-brand" type="button" onClick={() => navigate('/home')}>
          <span className="brand-mark">S</span>
          <span>ShortsFlow <small>AI studio</small></span>
        </button>
        <button
          className="mobile-menu-button"
          type="button"
          aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
          aria-controls="mobile-navigation"
          aria-expanded={mobileMenuOpen}
          onClick={() => setMobileMenuOpen((isOpen) => !isOpen)}
        >
          <span aria-hidden="true">{mobileMenuOpen ? '×' : '☰'}</span>
        </button>
      </header>
      {mobileMenuOpen && <button className="mobile-nav-backdrop" type="button" aria-label="Close navigation menu" onClick={() => setMobileMenuOpen(false)} />}
      {mobileMenuOpen && (
        <nav id="mobile-navigation" className="mobile-nav open" aria-label="Mobile navigation">
          {navigation.map((item) => {
            const isActive = isActiveRoute(item.route)
            return (
              <button
                className={`mobile-nav-item ${isActive ? 'active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
                type="button"
                key={item.route}
                onClick={() => navigate(item.route)}
              >
                <span className="nav-mark">{item.mark}</span>{item.label}
              </button>
            )
          })}
        </nav>
      )}
      <main className="main-content">{children}</main>
    </div>
  )
}
