import { useState } from 'react'

const TOOL_LABELS = {
  search_documents: 'Document search',
  query_records: 'Structured data lookup',
  calculate_metrics: 'Calculation',
  propose_action: 'Action proposed',
  execute_action: 'Action executed',
}

export default function ToolTrace({ trace }) {
  const [open, setOpen] = useState(false)
  if (!trace || trace.length === 0) return null

  return (
    <div className="tool-trace">
      <button className="trace-toggle" onClick={() => setOpen(!open)}>
        {open ? '▾' : '▸'} {trace.length} tool call{trace.length > 1 ? 's' : ''}:{' '}
        {trace.map((t) => TOOL_LABELS[t.tool] || t.tool).join(' → ')}
      </button>
      {open && (
        <div className="trace-details">
          {trace.map((t, i) => (
            <div key={i} className="trace-step">
              <div className="trace-step-name">{TOOL_LABELS[t.tool] || t.tool}</div>
              <pre className="trace-input">{JSON.stringify(t.input, null, 2)}</pre>
              <pre className="trace-result">{JSON.stringify(t.result, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
