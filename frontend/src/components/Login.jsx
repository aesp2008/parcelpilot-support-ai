import { useEffect, useState } from 'react'
import { listAccounts, login } from '../api.js'

export default function Login({ onLogin }) {
  const [accounts, setAccounts] = useState([])
  const [mode, setMode] = useState('customer')
  const [accountId, setAccountId] = useState('')
  const [role, setRole] = useState('agent')
  const [error, setError] = useState('')

  useEffect(() => {
    listAccounts().then((rows) => {
      setAccounts(rows)
      if (rows.length) setAccountId(rows[0].account_id)
    }).catch((e) => setError(e.message))
  }, [])

  const submit = async () => {
    setError('')
    try {
      const payload = mode === 'customer'
        ? { kind: 'customer', account_id: accountId }
        : { kind: 'internal', role }
      const session = await login(payload)
      onLogin(session)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="login-card">
      <h1>ParcelPilot Support AI</h1>
      <p className="subtitle">Mock sign-in &mdash; pick a context to try the assistant as.</p>

      <div className="tab-row">
        <button className={mode === 'customer' ? 'tab active' : 'tab'} onClick={() => setMode('customer')}>
          Customer
        </button>
        <button className={mode === 'internal' ? 'tab active' : 'tab'} onClick={() => setMode('internal')}>
          Internal Staff
        </button>
      </div>

      {mode === 'customer' ? (
        <label className="field">
          Account
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            {accounts.map((a) => (
              <option key={a.account_id} value={a.account_id}>
                {a.account_name} ({a.plan})
              </option>
            ))}
          </select>
        </label>
      ) : (
        <label className="field">
          Role
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="agent">Support Agent</option>
            <option value="manager">Manager</option>
          </select>
        </label>
      )}

      {error && <p className="error">{error}</p>}
      <button className="primary" onClick={submit}>Continue</button>
    </div>
  )
}
