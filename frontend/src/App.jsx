import { useEffect, useRef, useState } from 'react'
import { api, uuid } from './api.js'

const POLL_INTERVAL_MS = 2000

export default function App() {
  const [setup, setSetup] = useState({ credentials_saved: false, session_active: false })
  const [showCreds, setShowCreds] = useState(false)
  const [messages, setMessages] = useState([
    {
      role: 'bot',
      text: "Hi! I'm your Facebook agent. Tell me what to do — e.g. \"post about AI changing sales\" or \"comment on <fb-url> saying nice work\".",
    },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const chatEndRef = useRef(null)

  // Initial setup check
  useEffect(() => {
    refreshSetup()
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-open credentials modal if not configured
  useEffect(() => {
    if (!setup.credentials_saved) setShowCreds(true)
  }, [setup.credentials_saved])

  async function refreshSetup() {
    try {
      const s = await api.setupStatus()
      setSetup(s)
    } catch (e) {
      pushMsg({ role: 'error', text: `Couldn't reach backend: ${e.message}. Make sure FastAPI is running on :8000.` })
    }
  }

  function pushMsg(m) {
    setMessages((prev) => [...prev, m])
  }

  async function pollTask(taskId) {
    while (true) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
      try {
        const data = await api.getTask(taskId)
        if (data.status === 'done') return data
        if (data.status === 'error') return data
      } catch (e) {
        return { status: 'error', error: e.message }
      }
    }
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || busy) return
    if (!setup.credentials_saved) {
      setShowCreds(true)
      return
    }

    pushMsg({ role: 'user', text })
    setInput('')
    setBusy(true)

    const taskId = uuid()
    pushMsg({ role: 'bot', text: 'Working on it', pending: true, taskId })

    try {
      await api.sendChat(text, taskId)
      const result = await pollTask(taskId)

      setMessages((prev) =>
        prev.map((m) => {
          if (m.taskId !== taskId) return m
          if (result.status === 'error') {
            return { role: 'error', text: `Failed: ${result.error || 'unknown error'}` }
          }
          return {
            role: 'bot',
            text: result.result || 'Task complete.',
            generated: result.generated_content,
            action: result.action,
          }
        })
      )
    } catch (e) {
      setMessages((prev) =>
        prev.map((m) => (m.taskId === taskId ? { role: 'error', text: `Error: ${e.message}` } : m))
      )
    } finally {
      setBusy(false)
      refreshSetup()
    }
  }

  async function handleLogout() {
    try {
      await api.logout()
      pushMsg({ role: 'bot', text: 'Session cleared. Next task will re-login.' })
      refreshSetup()
    } catch (e) {
      pushMsg({ role: 'error', text: `Logout failed: ${e.message}` })
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Geodo FB Agent</h1>
          <div className="sub">Natural-language Facebook automation</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className={`status-pill ${setup.credentials_saved ? 'ok' : 'warn'}`}>
            {setup.credentials_saved ? 'Creds ✓' : 'No creds'}
          </span>
          <span className={`status-pill ${setup.session_active ? 'ok' : 'warn'}`}>
            {setup.session_active ? 'Session ✓' : 'No session'}
          </span>
          <button className="ghost" onClick={() => setShowCreds(true)}>Creds</button>
          <button className="ghost" onClick={handleLogout} disabled={!setup.session_active}>
            Logout
          </button>
        </div>
      </header>

      <div className="chat">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.pending ? (
              <span>
                {m.text}
                <span className="dots" />
              </span>
            ) : (
              <span>{m.text}</span>
            )}
            {m.generated && (
              <div className="gen">
                <strong>Generated {m.action}:</strong>
                <br />
                {m.generated}
              </div>
            )}
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      <div className="input-row">
        <input
          type="text"
          placeholder='e.g. "post about AI changing sales"'
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          disabled={busy}
        />
        <button onClick={handleSend} disabled={busy || !input.trim()}>
          {busy ? 'Working' : 'Send'}
        </button>
      </div>

      {showCreds && (
        <CredentialsModal
          onClose={() => setShowCreds(false)}
          onSaved={() => {
            setShowCreds(false)
            pushMsg({ role: 'bot', text: 'Credentials saved. You can send commands now.' })
            refreshSetup()
          }}
        />
      )}
    </div>
  )
}

function CredentialsModal({ onClose, onSaved }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleSave() {
    if (!email || !password) {
      setError('Both fields required.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await api.saveCredentials(email, password)
      onSaved()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Facebook Credentials</h2>
        <p>
          Stored locally and encrypted (Fernet/AES-128). Used only to log in to Facebook
          for the agent. Never sent anywhere else.
        </p>
        <label>Email</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          autoFocus
        />
        <label>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          onKeyDown={(e) => e.key === 'Enter' && handleSave()}
        />
        {error && <div style={{ color: 'var(--error)', fontSize: 13, marginBottom: 8 }}>{error}</div>}
        <div className="modal-actions">
          <button className="ghost" onClick={onClose} disabled={saving}>Cancel</button>
          <button onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
