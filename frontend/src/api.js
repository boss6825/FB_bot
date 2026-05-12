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
  saveCredentials: (email, password) =>
    jsonFetch('/auth/credentials', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => jsonFetch('/auth/logout', { method: 'POST' }),
  sendChat: (message, taskId) =>
    jsonFetch('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, task_id: taskId }),
    }),
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
  getTask: (taskId) => jsonFetch(`/task/${taskId}`),
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
