import { useEffect, useMemo, useRef, useState } from 'react';

/**
 * Animated "working" indicator for while a reply is in flight.
 *
 * Requests can run well past a minute — the model reasons before answering and
 * the agent may make several database and literature calls — so a single static
 * line gives no sense of whether anything is happening. The stages advance on a
 * timer that roughly tracks a real request, and an elapsed counter appears once
 * the wait becomes long enough to worry about.
 *
 * The stage labels describe what the agent typically does in that window; they
 * are not a live trace of tool calls.
 */
const STAGES = [
  { at: 0, label: 'Reading your question' },
  { at: 4, label: 'Checking variant databases' },
  { at: 12, label: 'Searching the literature' },
  { at: 24, label: 'Cross-referencing findings' },
  { at: 40, label: 'Working through the reasoning' },
  { at: 70, label: 'Composing the answer' },
];

// Thinking mode buys the model room to reason before it answers, so the same
// request takes substantially longer. The stages have to stretch to match:
// labels that run out and then sit on "Composing the answer" for another
// minute are worse than no labels at all.
const DEEP_STAGES = [
  { at: 0, label: 'Reading your question' },
  { at: 6, label: 'Checking variant databases' },
  { at: 18, label: 'Searching the literature' },
  { at: 34, label: 'Cross-referencing findings' },
  { at: 55, label: 'Weighing the evidence' },
  { at: 85, label: 'Working through the reasoning' },
  { at: 130, label: 'Writing up the reasoning' },
];

export default function ThinkingIndicator({ deep = false }) {
  const [elapsed, setElapsed] = useState(0);
  const started = useRef(Date.now());

  useEffect(() => {
    const id = setInterval(
      () => setElapsed(Math.floor((Date.now() - started.current) / 1000)),
      500
    );
    return () => clearInterval(id);
  }, []);

  const stages = deep ? DEEP_STAGES : STAGES;

  const stage = useMemo(() => {
    let current = stages[0];
    for (const s of stages) if (elapsed >= s.at) current = s;
    return current;
  }, [elapsed, stages]);

  return (
    <div className="thinking" role="status" aria-live="polite">
      <span className="thinking-orb" aria-hidden="true">
        <span className="thinking-orb-core" />
        <span className="thinking-orb-ring" />
      </span>

      <span className="thinking-label">{stage.label}</span>

      {/* The composer toggle is behind the message list while you wait, so say
          here which mode this answer is being written in. */}
      {deep && <span className="thinking-mode">Thinking</span>}

      <span className="thinking-dots" aria-hidden="true">
        <i /><i /><i />
      </span>

      {/* Only worth showing once the wait is long enough to be unnerving. */}
      {elapsed >= 8 && (
        <span className="thinking-elapsed">
          {elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`}
        </span>
      )}
    </div>
  );
}
