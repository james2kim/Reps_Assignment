import { useState } from 'react';

const STRATEGY_LABELS = {
  structured: 'Structured Lookup',
  document: 'Document Search',
  hybrid: 'Hybrid (Structured + Document)',
  none: 'No Retrieval',
};

export default function ThoughtTrace({ trace }) {
  const [open, setOpen] = useState(false);

  if (!trace) return null;

  return (
    <div className="thought-trace">
      <button className="trace-toggle" onClick={() => setOpen(!open)}>
        {open ? '▼' : '▶'} Thought Trace
        <span className="trace-badge">{trace.intent}</span>
      </button>
      {open && (
        <div className="trace-details">
          <div><strong>Intent:</strong> {trace.intent}</div>
          <div><strong>Strategy:</strong> {STRATEGY_LABELS[trace.strategy] || trace.strategy}</div>
          <div><strong>Confidence:</strong> {(trace.confidence * 100).toFixed(0)}%</div>
          <div><strong>Reason:</strong> {trace.reason}</div>
          <div><strong>Chunks Retrieved:</strong> {trace.chunks_retrieved}</div>
          <div><strong>Structured Data:</strong> {trace.structured_data ? 'Yes' : 'No'}</div>
        </div>
      )}
    </div>
  );
}
