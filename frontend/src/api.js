const BASE = '/api'

async function jsonFetch(url, opts = {}) {
  const res = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
  return data
}

export const api = {
  health: () => jsonFetch('/health'),
  setupStatus: () => jsonFetch('/status/setup'),

  // Login flow (user logs in manually via configured browser provider)
  startLogin: () => jsonFetch('/auth/login/start', { method: 'POST' }),
  verifyLogin: (sessionId) =>
    jsonFetch(`/auth/login/verify/${sessionId}`, { method: 'POST' }),
  cancelLogin: (sessionId) =>
    jsonFetch(`/auth/login/cancel/${sessionId}`, { method: 'POST' }),
  logout: () => jsonFetch('/auth/logout', { method: 'POST' }),

  // Draft / publish
  createDraft: (payloadOrMessage, taskId) => {
    const payload =
      typeof payloadOrMessage === 'string'
        ? { message: payloadOrMessage, task_id: taskId }
        : payloadOrMessage
    return jsonFetch('/draft', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  publishDraft: (draftId, text) =>
    jsonFetch(`/draft/${draftId}/publish`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  // Task polling
  getTask: (taskId) => jsonFetch(`/task/${taskId}`),
  confirmCaptchaSolved: (taskId) =>
    jsonFetch(`/task/${taskId}/captcha-solved`, { method: 'POST' }),
}

export function uuid() {
  return (
    crypto.randomUUID?.() ||
    'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      const v = c === 'x' ? r : (r & 0x3) | 0x8
      return v.toString(16)
    })
  )
}
