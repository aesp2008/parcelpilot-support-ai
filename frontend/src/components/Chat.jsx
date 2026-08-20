import { useRef, useState, useEffect } from 'react'
import { sendChat, confirmAction } from '../api.js'
import ToolTrace from './ToolTrace.jsx'

export default function Chat({ session }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', text }])
    setBusy(true)
    try {
      const res = await sendChat(session.session_id, text)
      setMessages((m) => [...m, {
        role: 'assistant', text: res.reply, trace: res.trace,
        pending: res.pending_actions,
      }])
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', text: `Error: ${e.message}` }])
    } finally {
      setBusy(false)
    }
  }

  const handleConfirm = async (msgIndex, pendingId, confirmed) => {
    if (!confirmed) {
      setMessages((m) => m.map((msg, i) => i === msgIndex
        ? { ...msg, pending: msg.pending.map((p) => p.pending_id === pendingId ? { ...p, dismissed: true } : p) }
        : msg))
      return
    }
    try {
      const result = await confirmAction(session.session_id, pendingId)
      setMessages((m) => [...m, {
        role: 'system',
        text: result.status === 'executed'
          ? `Action executed: ${result.action_type} (${result.action_id})`
          : `Could not execute action: ${result.error}`,
      }])
      setMessages((m) => m.map((msg, i) => i === msgIndex
        ? { ...msg, pending: msg.pending.map((p) => p.pending_id === pendingId ? { ...p, dismissed: true } : p) }
        : msg))
    } catch (e) {
      setMessages((m) => [...m, { role: 'system', text: `Error confirming action: ${e.message}` }])
    }
  }

  return (
    <div className="chat">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty-hint">
            Try: &ldquo;Can Northstar cancel ORD-1001 without a cancellation fee?&rdquo; or
            &ldquo;A pickup is three hours late because of carrier fault, should I get a service credit?&rdquo;
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            <div className="bubble">{m.text}</div>
            {m.trace && <ToolTrace trace={m.trace} />}
            {m.pending && m.pending.filter((p) => !p.dismissed).map((p) => (
              <div key={p.pending_id} className="confirm-box">
                <div className="confirm-summary">{p.summary}</div>
                {p.requires_manager_approval && (
                  <div className="confirm-flag">Requires manager approval to execute.</div>
                )}
                <div className="confirm-buttons">
                  <button className="confirm-yes" onClick={() => handleConfirm(i, p.pending_id, true)}>
                    Confirm
                  </button>
                  <button className="confirm-no" onClick={() => handleConfirm(i, p.pending_id, false)}>
                    Cancel
                  </button>
                </div>
              </div>
            ))}
          </div>
        ))}
        {busy && <div className="message assistant"><div className="bubble typing">Thinking…</div></div>}
        <div ref={bottomRef} />
      </div>
      <div className="composer">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="Ask about an order, policy, ticket…"
          rows={2}
        />
        <button className="primary" onClick={send} disabled={busy}>Send</button>
      </div>
    </div>
  )
}
