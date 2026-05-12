import { useState } from 'react'
import { api } from '../api.js'
import {
  IconAlertCircle, IconCheck, IconClose, IconEye, IconEyeOff, IconLogout,
} from './Icons.jsx'

export default function CredentialModal({ isSetup, onClose, onSave, onLogout }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loggingOut, setLoggingOut] = useState(false)

  async function handleSave() {
    if (!email.trim() || !password.trim()) {
      setError('Please fill in both fields')
      return
    }
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      await api.saveCredentials(email.trim(), password.trim())
      onSave()
    } catch (e) {
      setError(e.message || 'Could not connect to backend')
    } finally {
      setSaving(false)
    }
  }

  async function handleLogout() {
    setLoggingOut(true)
    setError('')
    setSuccess('')
    try {
      await api.logout()
      setSuccess('Credentials removed successfully. You can connect another account now.')
      await onLogout?.()
    } catch (e) {
      setError(e.message || 'Failed to logout')
    } finally {
      setLoggingOut(false)
    }
  }

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <h2 style={styles.title}>{isSetup ? 'Facebook Connection' : 'Connect Facebook'}</h2>
          <button style={styles.closeBtn} onClick={onClose} aria-label="Close">
            <IconClose size={18} />
          </button>
        </div>

        {isSetup ? (
          <div style={styles.body}>
            <div style={styles.connectedCard}>
              <div style={styles.connectedIcon}>
                <IconCheck size={20} />
              </div>
              <div>
                <div style={styles.connectedTitle}>Facebook Connected</div>
                <div style={styles.connectedSub}>
                  Your credentials are encrypted and stored securely.
                </div>
              </div>
            </div>
            <button
              style={styles.logoutBtn}
              onClick={handleLogout}
              disabled={loggingOut}
            >
              <IconLogout size={16} />
              {loggingOut ? 'Logging out...' : 'Disconnect & Clear Session'}
            </button>
            {error && (
              <div style={styles.error}>
                <IconAlertCircle size={14} />
                {error}
              </div>
            )}
            {success && (
              <div style={styles.success}>
                <IconCheck size={14} />
                {success}
              </div>
            )}
          </div>
        ) : (
          <div style={styles.body}>
            <p style={styles.description}>
              Enter your Facebook credentials. They are encrypted with AES-128 and stored
              locally on your server. Never sent anywhere else.
            </p>

            <div style={styles.field}>
              <label style={styles.label}>Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                style={styles.input}
                autoFocus
              />
            </div>

            <div style={styles.field}>
              <label style={styles.label}>Password</label>
              <div style={styles.passwordWrap}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{ ...styles.input, paddingRight: 42 }}
                  onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                />
                <button
                  style={styles.eyeBtn}
                  onClick={() => setShowPassword(!showPassword)}
                  type="button"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <IconEyeOff size={16} /> : <IconEye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div style={styles.error}>
                <IconAlertCircle size={14} />
                {error}
              </div>
            )}
            {success && (
              <div style={styles.success}>
                <IconCheck size={14} />
                {success}
              </div>
            )}

            <button
              style={{ ...styles.saveBtn, opacity: saving ? 0.7 : 1 }}
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Connecting...' : 'Connect Facebook'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

const styles = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(15, 23, 42, 0.4)',
    backdropFilter: 'blur(4px)',
    WebkitBackdropFilter: 'blur(4px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    animation: 'fadeIn 200ms ease',
  },
  modal: {
    background: '#fff',
    borderRadius: 16,
    width: 420,
    maxWidth: '90vw',
    boxShadow: '0 24px 80px rgba(0,0,0,0.15)',
    animation: 'fadeInUp 300ms ease',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '20px 24px',
    borderBottom: '1px solid var(--border)',
  },
  title: {
    fontSize: 17,
    fontWeight: 700,
    color: 'var(--text)',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--text-muted)',
    padding: 4,
    borderRadius: 6,
    display: 'flex',
    cursor: 'pointer',
  },
  body: {
    padding: 24,
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  description: {
    fontSize: 13,
    color: 'var(--text-secondary)',
    lineHeight: 1.6,
  },
  field: { display: 'flex', flexDirection: 'column', gap: 6 },
  label: { fontSize: 13, fontWeight: 600, color: 'var(--text)' },
  input: {
    padding: '10px 14px',
    borderRadius: 10,
    border: '1.5px solid var(--border)',
    fontSize: 14,
    outline: 'none',
    transition: 'border-color 150ms',
    width: '100%',
    background: 'var(--bg-alt)',
    color: 'var(--text)',
  },
  passwordWrap: { position: 'relative' },
  eyeBtn: {
    position: 'absolute',
    right: 10,
    top: '50%',
    transform: 'translateY(-50%)',
    background: 'none',
    border: 'none',
    color: 'var(--text-muted)',
    padding: 4,
    display: 'flex',
    cursor: 'pointer',
  },
  error: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 13,
    color: 'var(--error)',
    padding: '8px 12px',
    background: 'var(--error-light)',
    borderRadius: 8,
  },
  success: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 13,
    color: '#065F46',
    padding: '8px 12px',
    background: 'var(--success-light)',
    borderRadius: 8,
    border: '1px solid #D1FAE5',
  },
  saveBtn: {
    padding: '11px 20px',
    borderRadius: 10,
    border: 'none',
    background: 'var(--primary)',
    color: '#fff',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 150ms',
    marginTop: 4,
  },
  connectedCard: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    padding: 16,
    background: 'var(--success-light)',
    borderRadius: 12,
    border: '1px solid #D1FAE5',
  },
  connectedIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    background: '#10B981',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  connectedTitle: { fontSize: 14, fontWeight: 600, color: '#065F46' },
  connectedSub: { fontSize: 12, color: '#047857', marginTop: 2 },
  logoutBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: 10,
    borderRadius: 10,
    border: '1.5px solid var(--border)',
    background: '#fff',
    color: 'var(--text-secondary)',
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
  },
}
