const BASE = '/api'

// Render's free tier spins the backend down after 15 min idle; the first request after
// that can hit a proxy-level gateway error (520/502/503/504) while the process wakes up.
// Retrying once after a short delay covers that case without masking real failures.
const RETRYABLE_STATUSES = new Set([502, 503, 504, 520, 521, 522, 523, 524, 525, 526])

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function attempt(path, options) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = new Error(body.detail || `Request failed: ${res.status}`)
    err.status = res.status
    throw err
  }
  return res.json()
}

async function req(path, options = {}) {
  try {
    return await attempt(path, options)
  } catch (err) {
    const isRetryable = err.status === undefined || RETRYABLE_STATUSES.has(err.status)
    if (!isRetryable) throw err
    await sleep(2000)
    return attempt(path, options)
  }
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
