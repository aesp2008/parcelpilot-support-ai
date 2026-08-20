import { useEffect, useState } from 'react'
import { getInsights } from '../api.js'

export default function Insights({ session }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const load = () => {
    getInsights(session.session_id).then(setData).catch((e) => setError(e.message))
  }

  useEffect(load, [session.session_id])

  if (error) return <div className="error">{error}</div>
  if (!data) return <div>Loading…</div>

  return (
    <div className="insights">
      <div className="insights-header">
        <h2>Proactive Issue Detection</h2>
        <button onClick={load}>Refresh</button>
      </div>
      <p className="subtitle">
        Reference time: {data.generated_at_reference} &middot; {data.open_ticket_count} open tickets
      </p>

      {data.security_flags.length > 0 && (
        <section className="panel danger">
          <h3>Security-flagged tickets</h3>
          {data.security_flags.map((f) => (
            <div key={f.ticket_id} className="row">
              <strong>{f.ticket_id}</strong> ({f.account_id}) — {f.subject}
            </div>
          ))}
        </section>
      )}

      <section className="panel">
        <h3>SLA watch (sorted by urgency)</h3>
        <table>
          <thead>
            <tr><th>Ticket</th><th>Account</th><th>Subject</th><th>Sev.</th><th>Elapsed / Target (h)</th><th>Status</th></tr>
          </thead>
          <tbody>
            {data.sla_watch.map((r) => (
              <tr key={r.ticket_id} className={r.breached ? 'row-breach' : r.near_breach ? 'row-warn' : ''}>
                <td>{r.ticket_id}</td>
                <td>{r.account_name}</td>
                <td>{r.subject}</td>
                <td>{r.severity_heuristic}</td>
                <td>{r.elapsed_hours} / {r.target_hours}</td>
                <td>{r.breached ? 'BREACHED' : r.near_breach ? 'Near breach' : 'OK'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h3>Known-issue clusters (multi-customer impact)</h3>
        {data.known_issue_clusters.length === 0 && <p>No clustered known-issue tickets right now.</p>}
        {data.known_issue_clusters.map((c) => (
          <div key={c.known_issue} className="row">
            <strong>{c.known_issue}</strong> — {c.accounts_affected} account(s) affected:{' '}
            {c.tickets.map((t) => `${t.ticket_id} (${t.account_name})`).join(', ')}
          </div>
        ))}
      </section>
    </div>
  )
}
