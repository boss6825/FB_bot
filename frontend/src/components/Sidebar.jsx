import { useState } from 'react'
import {
  IconChat, IconDashboard, IconHistory, IconSettings, IconZap,
} from './Icons.jsx'

const NAV_ITEMS = [
  { id: 'chat', label: 'Chat', icon: IconChat },
  { id: 'dashboard', label: 'Dashboard', icon: IconDashboard },
  { id: 'history', label: 'History', icon: IconHistory },
]

export default function Sidebar({ currentPage, onNavigate, backendConnected, isSetup, onOpenSettings }) {
  const [hoveredItem, setHoveredItem] = useState(null)

  return (
    <aside style={styles.container}>
      <div style={styles.brand}>
        <div style={styles.logoCircle}>
          <IconZap size={18} />
        </div>
        <span style={styles.brandText}>FB Agent</span>
      </div>

      <nav style={styles.nav}>
        {NAV_ITEMS.map((item) => {
          const isActive = currentPage === item.id
          const isHovered = hoveredItem === item.id
          const Icon = item.icon
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              onMouseEnter={() => setHoveredItem(item.id)}
              onMouseLeave={() => setHoveredItem(null)}
              style={{
                ...styles.navItem,
                ...(isActive ? styles.navItemActive : {}),
                ...(isHovered && !isActive ? styles.navItemHover : {}),
              }}
            >
              <div style={{ ...styles.activeIndicator, opacity: isActive ? 1 : 0 }} />
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          )
        })}
      </nav>

      <div style={styles.bottomSection}>
        <button
          onClick={onOpenSettings}
          onMouseEnter={() => setHoveredItem('settings')}
          onMouseLeave={() => setHoveredItem(null)}
          style={{
            ...styles.navItem,
            ...(hoveredItem === 'settings' ? styles.navItemHover : {}),
          }}
        >
          <div style={{ ...styles.activeIndicator, opacity: 0 }} />
          <IconSettings size={18} />
          <span>Settings</span>
        </button>

        <div style={styles.statusBar}>
          <div
            style={{
              ...styles.statusDot,
              background: backendConnected ? (isSetup ? '#10B981' : '#F59E0B') : '#EF4444',
            }}
          />
          <span style={styles.statusText}>
            {backendConnected ? (isSetup ? 'Connected' : 'Setup needed') : 'Backend offline'}
          </span>
        </div>
      </div>
    </aside>
  )
}

const styles = {
  container: {
    width: 'var(--sidebar-width)',
    minWidth: 'var(--sidebar-width)',
    height: '100%',
    background: '#FAFBFD',
    borderRight: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    padding: 0,
    userSelect: 'none',
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '20px 20px 24px',
    borderBottom: '1px solid var(--border-light)',
  },
  logoCircle: {
    width: 34,
    height: 34,
    borderRadius: 10,
    background: 'var(--primary)',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandText: {
    fontSize: 16,
    fontWeight: 700,
    color: 'var(--text)',
    letterSpacing: '-0.3px',
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    padding: '12px 10px',
    flex: 1,
  },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 12px',
    borderRadius: 8,
    border: 'none',
    background: 'transparent',
    color: 'var(--text-secondary)',
    fontSize: 14,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 150ms ease',
    textAlign: 'left',
    width: '100%',
    position: 'relative',
  },
  navItemActive: {
    background: 'var(--primary-light)',
    color: 'var(--primary-text)',
    fontWeight: 600,
  },
  navItemHover: {
    background: 'var(--bg-muted)',
    color: 'var(--text)',
  },
  activeIndicator: {
    position: 'absolute',
    left: 0,
    top: '50%',
    transform: 'translateY(-50%)',
    width: 3,
    height: 20,
    borderRadius: '0 3px 3px 0',
    background: 'var(--primary)',
    transition: 'opacity 150ms ease',
  },
  bottomSection: {
    padding: '12px 10px 16px',
    borderTop: '1px solid var(--border-light)',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  statusBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 12px',
  },
  statusDot: {
    width: 7,
    height: 7,
    borderRadius: '50%',
    flexShrink: 0,
  },
  statusText: {
    fontSize: 12,
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
}
