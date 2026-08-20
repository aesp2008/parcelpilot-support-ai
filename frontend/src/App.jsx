import { useState } from 'react'
import Login from './components/Login.jsx'
import Chat from './components/Chat.jsx'

export default function App() {
  const [session, setSession] = useState(null)

  if (!session) return <Login onLogin={setSession} />

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">ParcelPilot Support AI</div>
        <div className="session-label">{session.label}</div>
        <nav>
          <button className="nav" onClick={() => setSession(null)}>Switch user</button>
        </nav>
      </header>
      <main>
        <Chat session={session} />
      </main>
    </div>
  )
}
