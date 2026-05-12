import { useEffect, useRef, useState } from 'react'
import {
  IconAlertCircle, IconCheck, IconEdit, IconHistory, IconLoader, IconSend, IconZap,
} from './Icons.jsx'

const QUICK_ACTIONS = [
  'Post about AI trends on Facebook',
  'Comment on the latest tech post',
  'Post a company update',
]

const STATUS_CONFIG = {
  processing: { color: 'var(--primary)', bg: 'var(--primary-light)', label: 'Processing', Icon: IconLoader },
  pending: { color: 'var(--warning)', bg: 'var(--warning-light)', label: 'Queued', Icon: IconHistory },
  running: { color: 'var(--primary)', bg: 'var(--primary-light)', label: 'Running', Icon: IconLoader },
  publishing: { color: 'var(--primary)', bg: 'var(--primary-light)', label: 'Publishing', Icon: IconLoader },
  done: { color: 'var(--success)', bg: 'var(--success-light)', label: 'Completed', Icon: IconCheck },
  error: { color: 'var(--error)', bg: 'var(--error-light)', label: 'Failed', Icon: IconAlertCircle },
}

function ThinkingDots() {
  return (
    <div style={{ display: 'flex', gap: 4, padding: '4px 0' }}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: 'var(--text-muted)',
            animation: `pulse 1.4s ease-in-out ${i * 0.16}s infinite`,
          }}
        />
      ))}
    </div>
  )
}

function BotAvatar() {
  return (
    <div
      style={{
        width: 32,
        height: 32,
        borderRadius: 10,
        background: 'var(--primary)',
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        fontSize: 13,
        fontWeight: 700,
      }}
    >
      <IconZap size={16} />
    </div>
  )
}

function TaskStatusCard({ task }) {
  const cfg = STATUS_CONFIG[task.status] || STATUS_CONFIG.pending
  const { Icon } = cfg
  return (
    <div
      style={{
        border: `1px solid ${task.status === 'error' ? '#FECACA' : 'var(--border)'}`,
        borderRadius: 12,
        padding: '14px 16px',
        background: '#fff',
        maxWidth: 440,
        animation: 'fadeInUp 300ms ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            background: cfg.bg,
            color: cfg.color,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Icon size={15} />
        </div>
        <span style={{ fontSize: 13, fontWeight: 600, color: cfg.color }}>{cfg.label}</span>
      </div>

      {task.result && task.status === 'done' && (
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
          {task.result}
        </p>
      )}
      {task.status === 'error' && (
        <p style={{ fontSize: 13, color: 'var(--error)', lineHeight: 1.5, margin: 0 }}>
          {task.error || task.result || 'Task failed.'}
        </p>
      )}
      {task.status === 'publishing' && (
        <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>
          Posting to Facebook via browser automation...
        </p>
      )}
      {task.status === 'running' && (
        <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>
          Executing browser automation...
        </p>
      )}
      {(task.status === 'pending' || task.status === 'processing') && (
        <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>
          Working on your command...
        </p>
      )}

      {task.generated && task.status === 'done' && (
        <div
          style={{
            marginTop: 10,
            padding: '10px 12px',
            background: 'var(--bg-alt)',
            borderLeft: '3px solid var(--primary)',
            borderRadius: 6,
            fontSize: 12,
            color: 'var(--text-secondary)',
            lineHeight: 1.5,
            whiteSpace: 'pre-wrap',
          }}
        >
          <strong style={{ color: 'var(--text)' }}>Published {task.action || 'content'}:</strong>
          <br />
          {task.generated}
        </div>
      )}
    </div>
  )
}

function DraftReviewCard({ draft, onPublish, onCancel, bubbleStyle }) {
  const [text, setText] = useState(draft.content || '')
  const publishing = draft.status === 'publishing'

  useEffect(() => {
    if (draft.content !== undefined) setText(draft.content)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.id])

  const rounded = bubbleStyle === 'rounded'

  return (
    <div
      style={{
        border: '1px solid var(--primary)',
        borderRadius: rounded ? 14 : 10,
        padding: 16,
        background: '#fff',
        maxWidth: 500,
        animation: 'fadeInUp 300ms ease',
        boxShadow: '0 4px 16px rgba(99, 102, 241, 0.08)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <div
          style={{
            width: 24,
            height: 24,
            borderRadius: 6,
            background: 'var(--primary-light)',
            color: 'var(--primary-text)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <IconEdit size={13} />
        </div>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--primary-text)' }}>
          Review draft — {draft.action || 'post'}
        </span>
      </div>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={publishing}
        rows={5}
        style={{
          width: '100%',
          background: 'var(--bg-alt)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: '10px 12px',
          fontSize: 14,
          color: 'var(--text)',
          outline: 'none',
          resize: 'vertical',
          minHeight: 90,
          lineHeight: 1.5,
          fontFamily: 'inherit',
        }}
      />

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginTop: 10,
        }}
      >
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{text.length} chars</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => onCancel(draft.id)}
            disabled={publishing}
            style={{
              padding: '7px 14px',
              borderRadius: 8,
              border: '1px solid var(--border)',
              background: '#fff',
              fontSize: 13,
              fontWeight: 500,
              color: 'var(--text-secondary)',
              cursor: publishing ? 'not-allowed' : 'pointer',
              opacity: publishing ? 0.5 : 1,
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => onPublish(draft.id, text)}
            disabled={publishing || !text.trim()}
            style={{
              padding: '7px 16px',
              borderRadius: 8,
              border: 'none',
              background: 'var(--primary)',
              color: '#fff',
              fontSize: 13,
              fontWeight: 600,
              cursor: publishing || !text.trim() ? 'not-allowed' : 'pointer',
              opacity: publishing || !text.trim() ? 0.6 : 1,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            {publishing ? <IconLoader size={13} /> : null}
            {publishing ? 'Publishing...' : 'Publish'}
          </button>
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ message, bubbleStyle, onPublishDraft, onCancelDraft }) {
  const rounded = bubbleStyle === 'rounded'

  if (message.type === 'thinking') {
    return (
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', animation: 'fadeInUp 200ms ease' }}>
        <BotAvatar />
        <div
          style={{
            padding: '12px 16px',
            borderRadius: rounded ? '4px 16px 16px 16px' : '4px 10px 10px 10px',
            background: 'var(--bg-alt)',
            border: '1px solid var(--border)',
          }}
        >
          <ThinkingDots />
        </div>
      </div>
    )
  }

  if (message.type === 'task') {
    return (
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', animation: 'fadeInUp 200ms ease' }}>
        <BotAvatar />
        <TaskStatusCard task={message.task} />
      </div>
    )
  }

  if (message.type === 'draft') {
    return (
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', animation: 'fadeInUp 200ms ease' }}>
        <BotAvatar />
        <DraftReviewCard
          draft={message.draft}
          onPublish={onPublishDraft}
          onCancel={onCancelDraft}
          bubbleStyle={bubbleStyle}
        />
      </div>
    )
  }

  if (message.type === 'error') {
    return (
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', animation: 'fadeInUp 200ms ease' }}>
        <BotAvatar />
        <div
          style={{
            padding: '12px 16px',
            borderRadius: rounded ? '4px 16px 16px 16px' : '4px 10px 10px 10px',
            background: 'var(--error-light)',
            border: '1px solid #FECACA',
            maxWidth: 440,
            fontSize: 14,
            color: '#991B1B',
            lineHeight: 1.5,
          }}
        >
          {message.content}
        </div>
      </div>
    )
  }

  if (message.type === 'bot') {
    return (
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', animation: 'fadeInUp 200ms ease' }}>
        <BotAvatar />
        <div
          style={{
            padding: '12px 16px',
            borderRadius: rounded ? '4px 16px 16px 16px' : '4px 10px 10px 10px',
            background: 'var(--bg-alt)',
            border: '1px solid var(--border)',
            maxWidth: 500,
            fontSize: 14,
            color: 'var(--text)',
            lineHeight: 1.6,
            whiteSpace: 'pre-wrap',
          }}
        >
          {message.content}
        </div>
      </div>
    )
  }

  // User message
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', animation: 'fadeInUp 200ms ease' }}>
      <div
        style={{
          padding: '12px 16px',
          borderRadius: rounded ? '16px 16px 4px 16px' : '10px 10px 4px 10px',
          background: 'var(--primary)',
          color: '#fff',
          maxWidth: 500,
          fontSize: 14,
          lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
        }}
      >
        {message.content}
      </div>
    </div>
  )
}

function WelcomeMessage({ onPickPrompt }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        flex: 1,
        gap: 16,
        padding: 40,
        animation: 'fadeIn 500ms ease',
      }}
    >
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: 16,
          background: 'var(--primary-light)',
          color: 'var(--primary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <IconZap size={28} />
      </div>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>FB Agent</h2>
      <p
        style={{
          fontSize: 14,
          color: 'var(--text-secondary)',
          textAlign: 'center',
          maxWidth: 360,
          lineHeight: 1.6,
        }}
      >
        Type a natural-language command to post or comment on Facebook. I'll generate a draft
        for you to review before publishing.
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', marginTop: 8 }}>
        {QUICK_ACTIONS.map((cmd, i) => (
          <button
            key={i}
            style={{
              padding: '8px 14px',
              borderRadius: 20,
              border: '1px solid var(--border)',
              background: '#fff',
              fontSize: 13,
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              transition: 'all 150ms',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--primary)'
              e.currentTarget.style.color = 'var(--primary)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.color = 'var(--text-secondary)'
            }}
            onClick={() => onPickPrompt(cmd)}
          >
            {cmd}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function ChatView({
  messages,
  onSendMessage,
  isSending,
  bubbleStyle = 'rounded',
  backendConnected,
  isSetup,
  onPublishDraft,
  onCancelDraft,
}) {
  const [inputValue, setInputValue] = useState('')
  const messagesScrollRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    const el = messagesScrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    const msg = inputValue.trim()
    if (!msg || isSending) return
    setInputValue('')
    onSendMessage(msg)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const pickPrompt = (cmd) => {
    setInputValue(cmd)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  const statusDot = backendConnected ? (isSetup ? 'var(--success)' : 'var(--warning)') : 'var(--error)'
  const statusLabel = backendConnected ? (isSetup ? 'Live' : 'Setup needed') : 'Offline'

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.headerTitle}>Chat</h1>
        <div style={styles.headerBadge}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: statusDot }} />
          <span>{statusLabel}</span>
        </div>
      </div>

      <div style={styles.messagesArea} ref={messagesScrollRef}>
        {messages.length === 0 ? (
          <WelcomeMessage onPickPrompt={pickPrompt} />
        ) : (
          <div style={styles.messagesList}>
            {messages.map((msg, i) => (
              <MessageBubble
                key={msg.id || i}
                message={msg}
                bubbleStyle={bubbleStyle}
                onPublishDraft={onPublishDraft}
                onCancelDraft={onCancelDraft}
              />
            ))}
          </div>
        )}
      </div>

      <div style={styles.inputArea}>
        <div style={styles.inputWrap}>
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command... e.g. 'post about AI trends'"
            style={styles.input}
            disabled={isSending}
          />
          <button
            onClick={handleSend}
            disabled={!inputValue.trim() || isSending}
            style={{
              ...styles.sendBtn,
              opacity: inputValue.trim() && !isSending ? 1 : 0.4,
              cursor: !inputValue.trim() || isSending ? 'not-allowed' : 'pointer',
            }}
            aria-label="Send"
          >
            {isSending ? <IconLoader size={18} /> : <IconSend size={18} />}
          </button>
        </div>
        <div style={styles.inputHint}>
          <span>Enter</span> to send &nbsp;·&nbsp; <span>Shift+Enter</span> for new line
        </div>
      </div>
    </div>
  )
}

const styles = {
  container: { display: 'flex', flexDirection: 'column', height: '100%', flex: 1 },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '18px 28px',
    borderBottom: '1px solid var(--border)',
    background: '#fff',
    flexShrink: 0,
  },
  headerTitle: { fontSize: 18, fontWeight: 700, color: 'var(--text)' },
  headerBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 12,
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  messagesArea: {
    flex: 1,
    overflowY: 'auto',
    padding: '24px 28px',
    display: 'flex',
    flexDirection: 'column',
  },
  messagesList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
    maxWidth: 680,
    width: '100%',
    margin: '0 auto',
  },
  inputArea: {
    padding: '16px 28px 20px',
    borderTop: '1px solid var(--border)',
    background: '#fff',
    flexShrink: 0,
  },
  inputWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    background: 'var(--bg-alt)',
    border: '1.5px solid var(--border)',
    borderRadius: 14,
    padding: '4px 4px 4px 16px',
    maxWidth: 680,
    margin: '0 auto',
    transition: 'border-color 200ms',
  },
  input: {
    flex: 1,
    border: 'none',
    background: 'transparent',
    fontSize: 14,
    outline: 'none',
    color: 'var(--text)',
    padding: '8px 0',
  },
  sendBtn: {
    width: 40,
    height: 40,
    borderRadius: 10,
    border: 'none',
    background: 'var(--primary)',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'all 150ms',
    flexShrink: 0,
  },
  inputHint: {
    textAlign: 'center',
    fontSize: 11,
    color: 'var(--text-muted)',
    marginTop: 8,
  },
}
