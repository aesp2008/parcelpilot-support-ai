const BASE = '/api'

async function req(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

export const listAccounts = () => req('/accounts')

export const login = (payload) =>
  req('/login', { method: 'POST', body: JSON.stringify(payload) })

export const sendChat = (session_id, message) =>
  req('/chat', { method: 'POST', body: JSON.stringify({ session_id, message }) })

export const confirmAction = (session_id, pending_id) =>
  req('/actions/confirm', { method: 'POST', body: JSON.stringify({ session_id, pending_id }) })

export const getInsights = (session_id) =>
  req(`/insights?session_id=${encodeURIComponent(session_id)}`)
