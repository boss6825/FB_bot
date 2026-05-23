import { useCallback, useEffect, useRef, useState } from 'react'
import { api, uuid } from './api.js'
import Sidebar from './components/Sidebar.jsx'
import ChatView from './components/ChatView.jsx'
import DashboardView from './components/DashboardView.jsx'
import HistoryView from './components/HistoryView.jsx'
import CredentialModal from './components/CredentialModal.jsx'

const POLL_INTERVAL_MS = 2000
const POLL_MAX_ATTEMPTS = 240 // 8 minutes
const TASK_STORAGE_KEY = 'fb_agent_tasks'

function loadTasks() {
  try {
    return JSON.parse(localStorage.getItem(TASK_STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function saveTasks(tasks) {
  try {
    localStorage.setItem(TASK_STORAGE_KEY, JSON.stringify(tasks))
  } catch {
    /* ignore */
  }
}

export default function App() {
  const [page, setPage] = useState('chat')
  const [messages, setMessages] = useState([])
  const [tasks, setTasks] = useState(loadTasks)
  const [backendConnected, setBackendConnected] = useState(false)
  const [isSetup, setIsSetup] = useState(false)
  const [showCredModal, setShowCredModal] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const credModalAutoShown = useRef(false)

  // Persist tasks
  useEffect(() => {
    saveTasks(tasks)
  }, [tasks])

  // Backend health + setup polling
  useEffect(() => {
    checkBackend()
    const interval = setInterval(checkBackend, 30000)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function checkBackend() {
    try {
      await api.health()
      setBackendConnected(true)
      try {
        const setup = await api.setupStatus()
        const ok = !!setup.logged_in
        setIsSetup(ok)
        if (!ok && !credModalAutoShown.current) {
          credModalAutoShown.current = true
          setShowCredModal(true)
        }
      } catch {
        /* ignore */
      }
    } catch {
      setBackendConnected(false)
    }
  }

  // ── Message helpers ──────────────────────────────────────────────
  const pushMessage = useCallback((msg) => {
    const m = { id: uuid(), timestamp: Date.now(), ...msg }
    setMessages((prev) => [...prev, m])
    return m.id
  }, [])

  const updateMessage = useCallback((id, updates) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...updates } : m)))
  }, [])

  const replaceMessage = useCallback((id, newMsg) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { id: m.id, timestamp: m.timestamp, ...newMsg } : m)),
    )
  }, [])

  const removeMessage = useCallback((id) => {
    setMessages((prev) => prev.filter((m) => m.id !== id))
  }, [])

  // ── Task store helpers ───────────────────────────────────────────
  const upsertTask = useCallback((taskId, patch) => {
    setTasks((prev) => ({
      ...prev,
      [taskId]: { id: taskId, ...(prev[taskId] || {}), ...patch },
    }))
  }, [])

  // ── Polling ──────────────────────────────────────────────────────
  async function pollUntil(taskId, terminalStatuses) {
    let attempts = 0
    while (attempts < POLL_MAX_ATTEMPTS) {
      attempts++
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
      try {
        const data = await api.getTask(taskId)
        if (terminalStatuses.includes(data.status)) return data
      } catch (e) {
        if (attempts >= 3) return { status: 'error', error: e.message || 'Lost connection' }
      }
    }
    return { status: 'error', error: 'Task timed out.' }
  }

  // ── Send command → create draft ──────────────────────────────────
  const handleSendMessage = useCallback(
    async (payload) => {
      if (isSending) return

      const isStructured = typeof payload === 'object' && payload !== null
      const text = isStructured ? payload.messagePreview || payload.contentBrief || '' : payload
      const commandText =
        isStructured && payload.mode === 'comment'
          ? `Comment on ${payload.targetUrl} saying: ${payload.contentBrief}`
          : text

      pushMessage({ type: 'user', content: commandText })

      if (!backendConnected) {
        pushMessage({
          type: 'error',
          content:
            'Backend is offline. Start the server with: uvicorn main:app --reload --port 8000',
        })
        return
      }
      if (!isSetup) {
        pushMessage({
          type: 'error',
          content: 'Please connect your Facebook account first.',
        })
        setShowCredModal(true)
        return
      }

      const thinkingId = pushMessage({ type: 'thinking' })
      setIsSending(true)

      const taskId = uuid()
      const draftPayload =
        isStructured && payload.mode === 'comment'
          ? {
              task_id: taskId,
              action: 'comment',
              target_url: payload.targetUrl,
              content_brief: payload.contentBrief,
              message: payload.messagePreview,
            }
          : {
              task_id: taskId,
              message: text,
            }

      upsertTask(taskId, {
        command: commandText,
        status: 'processing',
        timestamp: Date.now(),
      })

      try {
        await api.createDraft(draftPayload)
        const result = await pollUntil(taskId, ['draft', 'error'])

        if (result.status === 'error') {
          const errMsg = result.error || 'Failed to create draft.'
          upsertTask(taskId, { status: 'error', error: errMsg, completedAt: Date.now() })
          replaceMessage(thinkingId, {
            type: 'task',
            task: {
              id: taskId,
              status: 'error',
              command: commandText,
              error: errMsg,
            },
          })
          setIsSending(false)
          return
        }

        // Draft ready
        const generated = result.generated_content || ''
        const action = result.action || 'post'
        upsertTask(taskId, {
          status: 'draft',
          generated,
          action,
        })

        replaceMessage(thinkingId, {
          type: 'draft',
          draft: {
            id: taskId,
            action,
            content: generated,
            status: 'draft',
          },
        })
      } catch (e) {
        const errMsg = e.message || 'Failed to send command.'
        upsertTask(taskId, { status: 'error', error: errMsg, completedAt: Date.now() })
        replaceMessage(thinkingId, {
          type: 'error',
          content: errMsg,
        })
      } finally {
        setIsSending(false)
      }
    },
    [backendConnected, isSetup, isSending, pushMessage, replaceMessage, upsertTask],
  )

  // ── Helper: handle captcha_required during polling ──────────────
  async function pollUntilWithCaptcha(taskId, terminalStatuses, thinkingOrDraftId) {
    let attempts = 0
    while (attempts < POLL_MAX_ATTEMPTS) {
      attempts++
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
      try {
        const data = await api.getTask(taskId)

        if (data.status === 'captcha_required') {
          // Show captcha card, replacing thinking indicator if present
          const captchaMsg = {
            type: 'captcha',
            captcha: {
              taskId,
              captcha_type: data.captcha_type,
              details: data.captcha_details,
              sessionUrl: data.session_url,
            },
          }

          setMessages((prev) => {
            const alreadyHasCaptcha = prev.some(
              (m) => m.type === 'captcha' && m.captcha?.taskId === taskId,
            )
            if (alreadyHasCaptcha) return prev

            if (thinkingOrDraftId) {
              return prev.map((m) =>
                m.id === thinkingOrDraftId
                  ? { ...m, ...captchaMsg }
                  : m,
              )
            }
            return [...prev, { id: uuid(), timestamp: Date.now(), ...captchaMsg }]
          })
          // Keep polling — the agent is waiting for the event
          continue
        }

        if (terminalStatuses.includes(data.status)) return data
      } catch (e) {
        if (attempts >= 3) return { status: 'error', error: e.message || 'Lost connection' }
      }
    }
    return { status: 'error', error: 'Task timed out.' }
  }

  // ── Publish a draft ──────────────────────────────────────────────
  const handlePublishDraft = useCallback(
    async (draftId, finalText) => {
      const trimmed = (finalText || '').trim()
      if (!trimmed) return

      // Find draft message and flip its status to 'publishing'
      const draftMsgId = messages.find(
        (m) => m.type === 'draft' && m.draft?.id === draftId,
      )?.id

      setMessages((prev) =>
        prev.map((m) =>
          m.type === 'draft' && m.draft?.id === draftId
            ? { ...m, draft: { ...m.draft, content: trimmed, status: 'publishing' } }
            : m,
        ),
      )

      upsertTask(draftId, { status: 'publishing', generated: trimmed })

      try {
        await api.publishDraft(draftId, trimmed)
        const result = await pollUntilWithCaptcha(draftId, ['done', 'error'], draftMsgId)

        const completedAt = Date.now()

        // Remove any captcha card for this task
        setMessages((prev) =>
          prev.filter((m) => !(m.type === 'captcha' && m.captcha?.taskId === draftId)),
        )

        if (result.status === 'error') {
          const errMsg = result.error || 'Failed to publish.'
          upsertTask(draftId, {
            status: 'error',
            error: errMsg,
            completedAt,
          })
          setMessages((prev) =>
            prev.map((m) =>
              m.type === 'draft' && m.draft?.id === draftId
                ? {
                    ...m,
                    type: 'task',
                    task: {
                      id: draftId,
                      status: 'error',
                      error: errMsg,
                      generated: trimmed,
                    },
                    draft: undefined,
                  }
                : m,
            ),
          )
          return
        }

        const action = tasks[draftId]?.action || result.action || 'post'
        upsertTask(draftId, {
          status: 'done',
          result: result.result || 'Posted!',
          generated: trimmed,
          action,
          completedAt,
        })

        setMessages((prev) =>
          prev.map((m) =>
            m.type === 'draft' && m.draft?.id === draftId
              ? {
                  ...m,
                  type: 'task',
                  task: {
                    id: draftId,
                    status: 'done',
                    result: result.result || 'Posted!',
                    generated: trimmed,
                    action,
                  },
                  draft: undefined,
                }
              : m,
          ),
        )
      } catch (e) {
        const errMsg = e.message || 'Failed to publish.'
        upsertTask(draftId, { status: 'error', error: errMsg, completedAt: Date.now() })
        setMessages((prev) =>
          prev.map((m) =>
            m.type === 'draft' && m.draft?.id === draftId
              ? {
                  ...m,
                  type: 'task',
                  task: { id: draftId, status: 'error', error: errMsg },
                  draft: undefined,
                }
              : m,
          ),
        )
      }
    },
    [tasks, upsertTask, messages],
  )

  // ── CAPTCHA solved handler ────────────────────────────────────────
  const handleCaptchaSolved = useCallback(
    async (taskId) => {
      try {
        await api.confirmCaptchaSolved(taskId)
      } catch {
        // Endpoint may 404 if agent already moved on — that's fine
      }
      // Replace captcha card with thinking dots while agent resumes
      setMessages((prev) =>
        prev.map((m) =>
          m.type === 'captcha' && m.captcha?.taskId === taskId
            ? { ...m, type: 'thinking', captcha: undefined }
            : m,
        ),
      )
    },
    [],
  )

  const handleCancelDraft = useCallback(
    (draftId) => {
      setMessages((prev) =>
        prev
          .filter((m) => !(m.type === 'draft' && m.draft?.id === draftId))
          .concat([
            {
              id: uuid(),
              timestamp: Date.now(),
              type: 'bot',
              content: 'Draft cancelled. Send another command when you’re ready.',
            },
          ]),
      )
      setTasks((prev) => {
        const copy = { ...prev }
        delete copy[draftId]
        return copy
      })
    },
    [],
  )

  // ── Refresh handler for dashboard ────────────────────────────────
  const handleDashboardRefresh = useCallback(() => {
    checkBackend()
  }, [])

  return (
    <div style={styles.layout}>
      <Sidebar
        currentPage={page}
        onNavigate={setPage}
        backendConnected={backendConnected}
        isSetup={isSetup}
        onOpenSettings={() => setShowCredModal(true)}
      />
      <main style={styles.main}>
        {page === 'chat' && (
          <ChatView
            messages={messages}
            onSendMessage={handleSendMessage}
            isSending={isSending}
            bubbleStyle="rounded"
            backendConnected={backendConnected}
            isSetup={isSetup}
            onPublishDraft={handlePublishDraft}
            onCancelDraft={handleCancelDraft}
            onCaptchaSolved={handleCaptchaSolved}
          />
        )}
        {page === 'dashboard' && (
          <DashboardView tasks={tasks} onRefresh={handleDashboardRefresh} />
        )}
        {page === 'history' && <HistoryView tasks={tasks} />}
      </main>

      {showCredModal && (
        <CredentialModal
          isSetup={isSetup}
          onClose={() => setShowCredModal(false)}
          onSave={() => {
            setIsSetup(true)
            setShowCredModal(false)
            checkBackend()
          }}
          onLogout={async () => {
            setIsSetup(false)
            await checkBackend()
          }}
        />
      )}
    </div>
  )
}

const styles = {
  layout: {
    display: 'flex',
    height: '100vh',
    width: '100vw',
    overflow: 'hidden',
    background: 'var(--bg-alt)',
  },
  main: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
    background: '#fff',
  },
}
