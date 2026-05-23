import { useState } from 'react'
import { api } from '../api.js'
import {
  IconAlertCircle, IconCheck, IconClose, IconLoader, IconLogout,
} from './Icons.jsx'

const IconExternalLink = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
  </svg>
)

/**
 * Login modal — the user logs into Facebook manually via a Browserbase
 * cloud browser session.  No credentials are stored on the backend.
 *
 * States: idle → starting → waiting → verifying → (success | error)
 */
export default function CredentialModal({ isSetup, onClose, onSave, onLogout }) {
  const [phase, setPhase] = useState('idle') // idle | starting | waiting | verifying
  const [sessionId, setSessionId] = useState(null)
  const [sessionUrl, setSessionUrl] = useState(null)
  const [liveViewUrl, setLiveViewUrl] = useState(null)
  const [error, setError] = useState('')
  const [verifyHint, setVerifyHint] = useState('')
  const [loggingOut, setLoggingOut] = useState(false)

  async function handleStartLogin() {
    setPhase('starting')
    setError('')
    setVerifyHint('')
    try {
      const data = await api.startLogin()
      setSessionId(data.session_id)
      setSessionUrl(data.session_url)
      setLiveViewUrl(data.live_view_url || null)
      setPhase('waiting')
    } catch (e) {
      setError(e.message || 'Failed to start login session')
      setPhase('idle')
    }
  }

  async function handleVerify() {
    if (!sessionId) return
    setPhase('verifying')
    setVerifyHint('')
    setError('')
    try {
      const data = await api.verifyLogin(sessionId)
      if (data.status === 'logged_in') {
        onSave()
      } else {
        const hint =
          data.state === 'login'
            ? 'You are still on the login page. Please finish logging in.'
            : data.state === 'captcha' || data.state === 'checkpoint'
              ? 'A security challenge is showing. Please solve it first.'
              : 'Login not detected yet. Please finish logging in.'
        setVerifyHint(hint)
        setPhase('waiting')
      }
    } catch (e) {
      setError(e.message || 'Verification failed')
      setPhase('waiting')
    }
  }

  async function handleCancel() {
    if (sessionId) {
      try { await api.cancelLogin(sessionId) } catch { /* ok */ }
    }
    setSessionId(null)
    setSessionUrl(null)
    setLiveViewUrl(null)
    setPhase('idle')
    setError('')
    setVerifyHint('')
  }

  async function handleLogout() {
    setLoggingOut(true)
    setError('')
    try {
      await api.logout()
      await onLogout?.()
    } catch (e) {
      setError(e.message || 'Failed to logout')
    } finally {
      setLoggingOut(false)
    }
  }

  // ── Connected state ──────────────────────────────────────────
  if (isSetup) {
    return (
      <div style={styles.overlay} onClick={onClose}>
        <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
          <div style={styles.header}>
            <h2 style={styles.title}>Facebook Connection</h2>
            <button style={styles.closeBtn} onClick={onClose} aria-label="Close">
              <IconClose size={18} />
            </button>
          </div>
          <div style={styles.body}>
            <div style={styles.connectedCard}>
              <div style={styles.connectedIcon}>
                <IconCheck size={20} />
              </div>
              <div>
                <div style={styles.connectedTitle}>Facebook Connected</div>
                <div style={styles.connectedSub}>
                  Your session cookies are saved in Browserbase. No passwords stored.
                </div>
              </div>
            </div>
            <button
              style={styles.logoutBtn}
              onClick={handleLogout}
              disabled={loggingOut}
            >
              <IconLogout size={16} />
              {loggingOut ? 'Disconnecting...' : 'Disconnect & Clear Session'}
            </button>
            {error && (
              <div style={styles.error}>
                <IconAlertCircle size={14} />
                {error}
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ── Login flow ───────────────────────────────────────────────
  return (
    <div style={styles.overlay} onClick={phase === 'idle' ? onClose : undefined}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <h2 style={styles.title}>Connect Facebook</h2>
          <button
            style={styles.closeBtn}
            onClick={phase === 'waiting' ? handleCancel : onClose}
            aria-label="Close"
          >
            <IconClose size={18} />
          </button>
        </div>

        <div style={styles.body}>
          {phase === 'idle' && (
            <>
              <p style={styles.description}>
                Log into Facebook in a secure cloud browser. No credentials are stored
                on this server — only session cookies are saved for automation.
              </p>
              <button style={styles.primaryBtn} onClick={handleStartLogin}>
                Login to Facebook
              </button>
            </>
          )}

          {phase === 'starting' && (
            <div style={styles.loadingWrap}>
              <IconLoader size={24} />
              <p style={styles.loadingText}>Starting browser session...</p>
            </div>
          )}

          {(phase === 'waiting' || phase === 'verifying') && (
            <>
              <div style={styles.banner}>
                <span>
                  Navigate to <strong>facebook.com</strong> in the URL bar below,
                  log in (handle any OTP / 2FA), then click <strong>I&apos;m Logged In</strong>.
                </span>
                {sessionUrl && (
                  <a
                    href={sessionUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={styles.openInTabLink}
                  >
                    <IconExternalLink size={12} />
                    Open in new tab
                  </a>
                )}
              </div>

              {liveViewUrl ? (
                <iframe
                  title="Facebook Login (Browserbase Live View)"
                  src={liveViewUrl}
                  style={styles.liveView}
                  sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-pointer-lock"
                  allow="clipboard-read; clipboard-write"
                />
              ) : (
                <div style={styles.iframeFallback}>
                  <IconAlertCircle size={14} />
                  <span>
                    Live view isn&apos;t available. {sessionUrl ? (
                      <a href={sessionUrl} target="_blank" rel="noopener noreferrer">
                        Open the session in a new tab
                      </a>
                    ) : 'Try again.'}
                  </span>
                </div>
              )}

              {verifyHint && (
                <div style={styles.warning}>
                  <IconAlertCircle size={14} />
                  {verifyHint}
                </div>
              )}

              <div style={styles.buttonRow}>
                <button style={styles.secondaryBtn} onClick={handleCancel}>
                  Cancel
                </button>
                <button
                  style={{
                    ...styles.primaryBtn,
                    opacity: phase === 'verifying' ? 0.7 : 1,
                  }}
                  onClick={handleVerify}
                  disabled={phase === 'verifying'}
                >
                  {phase === 'verifying' ? (
                    <>
                      <IconLoader size={14} />
                      Checking...
                    </>
                  ) : (
                    "I'm Logged In"
                  )}
                </button>
              </div>
            </>
          )}

          {error && (
            <div style={styles.error}>
              <IconAlertCircle size={14} />
              {error}
            </div>
          )}
        </div>
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
    width: 960,
    maxWidth: '94vw',
    maxHeight: '92vh',
    boxShadow: '0 24px 80px rgba(0,0,0,0.15)',
    animation: 'fadeInUp 300ms ease',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
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
    margin: 0,
  },
  primaryBtn: {
    padding: '11px 20px',
    borderRadius: 10,
    border: 'none',
    background: 'var(--primary)',
    color: '#fff',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 150ms',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  secondaryBtn: {
    padding: '10px 18px',
    borderRadius: 10,
    border: '1.5px solid var(--border)',
    background: '#fff',
    fontSize: 13,
    fontWeight: 500,
    color: 'var(--text-secondary)',
    cursor: 'pointer',
  },
  buttonRow: {
    display: 'flex',
    gap: 10,
    justifyContent: 'flex-end',
  },
  loadingWrap: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 12,
    padding: '20px 0',
    color: 'var(--primary)',
  },
  loadingText: {
    fontSize: 14,
    color: 'var(--text-secondary)',
    margin: 0,
  },
  instructionCard: {
    display: 'flex',
    gap: 14,
    padding: 14,
    background: 'var(--bg-alt)',
    borderRadius: 12,
    border: '1px solid var(--border)',
  },
  stepNumber: {
    width: 28,
    height: 28,
    borderRadius: 8,
    background: 'var(--primary-light)',
    color: 'var(--primary-text)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 13,
    fontWeight: 700,
    flexShrink: 0,
  },
  stepTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: 'var(--text)',
    marginBottom: 2,
  },
  stepSub: {
    fontSize: 12,
    color: 'var(--text-secondary)',
    lineHeight: 1.5,
  },
  banner: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    padding: '10px 14px',
    background: 'var(--primary-light)',
    border: '1px solid var(--border)',
    borderRadius: 10,
    fontSize: 13,
    color: 'var(--text-secondary)',
  },
  openInTabLink: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    fontSize: 12,
    color: 'var(--primary-text)',
    textDecoration: 'none',
    fontWeight: 600,
    flexShrink: 0,
  },
  liveView: {
    width: '100%',
    height: 560,
    minHeight: 420,
    border: '1px solid var(--border)',
    borderRadius: 12,
    background: '#000',
    display: 'block',
  },
  iframeFallback: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '14px 16px',
    background: 'var(--error-light)',
    border: '1px solid #FECACA',
    borderRadius: 10,
    fontSize: 13,
    color: 'var(--error)',
  },
  openBrowserBtn: {
    padding: '10px 16px',
    borderRadius: 10,
    border: '1.5px solid var(--primary)',
    background: 'var(--primary-light)',
    fontSize: 14,
    fontWeight: 600,
    color: 'var(--primary-text)',
    textDecoration: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    transition: 'all 150ms',
  },
  warning: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 13,
    color: '#92400E',
    padding: '8px 12px',
    background: '#FEF3C7',
    borderRadius: 8,
    border: '1px solid #FDE68A',
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
