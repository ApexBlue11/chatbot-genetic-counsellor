/**
 * The dot that tells a visitor whether the backend is awake.
 *
 * The demo backend sleeps when idle, so a first-time visitor can click around
 * for a minute with nothing happening. Amber means "still waking, hold on",
 * green means "you can start a conversation now".
 */
const LABELS = {
  connecting: { text: 'Connecting…', tone: 'amber', hint: 'Checking the analysis server.' },
  waking: {
    text: 'Waking the server…',
    tone: 'amber',
    hint: 'The demo server sleeps when idle. This usually takes under a minute.',
  },
  online: { text: 'Connected', tone: 'green', hint: 'Ready — you can start a conversation.' },
  offline: {
    text: 'Server unavailable',
    tone: 'red',
    hint: "Couldn't reach the analysis server. Try again in a moment.",
  },
};

export default function ConnectionStatus({ status, onRetry, variant = 'inline' }) {
  const info = LABELS[status] ?? LABELS.connecting;
  const pulsing = status === 'connecting' || status === 'waking';

  return (
    <span
      className={`conn-status conn-status--${info.tone} conn-status--${variant}`}
      title={info.hint}
      role="status"
      aria-live="polite"
    >
      <span className={`conn-dot${pulsing ? ' conn-dot--pulse' : ''}`} />
      <span className="conn-label">{info.text}</span>
      {status === 'offline' && onRetry && (
        <button type="button" className="conn-retry" onClick={onRetry}>
          Retry
        </button>
      )}
    </span>
  );
}

export { LABELS as CONNECTION_LABELS };
