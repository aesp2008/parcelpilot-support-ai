import { useState } from 'react'
import Login from './components/Login.jsx'
import Chat from './components/Chat.jsx'
import Insights from './components/Insights.jsx'

export default function App() {
  const [session, setSession] = useState(null)
  const [view, setView] = useState('chat')

  if (!session) return <Login onLogin={setSession} />

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">ParcelPilot Support AI</div>
        <div className="session-label">{session.label}</div>
        <nav>
          <button className={view === 'chat' ? 'nav active' : 'nav'} onClick={() => setView('chat')}>Chat</button>
          {session.kind === 'internal' && (
            <button className={view === 'insights' ? 'nav active' : 'nav'} onClick={() => setView('insights')}>
              Insights
            </button>
          )}
          <button className="nav" onClick={() => setSession(null)}>Switch user</button>
        </nav>
      </header>
      <main>
        {view === 'chat' ? <Chat session={session} /> : <Insights session={session} />}
      </main>
    </div>
  )
}
