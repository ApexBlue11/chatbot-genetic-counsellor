import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../services/api';

/**
 * Tracks whether the backend is reachable.
 *
 * The demo backend runs on a host that idles its container, so the first
 * request after a quiet period can take up to a minute while it wakes. Until
 * this hook existed there was no way for a visitor to tell the difference
 * between "still waking" and "broken" — they would click New Conversation and
 * nothing would happen.
 *
 * Returns one of:
 *   'connecting' — first probe in flight, nothing known yet
 *   'waking'     — probes are failing but we are still retrying
 *   'online'     — backend answered
 *   'offline'    — gave up after RETRY_LIMIT attempts
 */
const POLL_WHEN_ONLINE = 60000;
const RETRY_BASE = 2500;
const RETRY_LIMIT = 40;            // ~2 minutes of retries, well past a cold start
const WAKING_AFTER_ATTEMPTS = 1;

export default function useBackendStatus() {
  const [status, setStatus] = useState('connecting');
  const [attempts, setAttempts] = useState(0);
  const timerRef = useRef(null);
  const cancelled = useRef(false);
  const attemptRef = useRef(0);

  const schedule = useCallback((delay) => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => { probeRef.current(); }, delay);
  }, []);

  const probeRef = useRef(async () => {});

  probeRef.current = async () => {
    if (cancelled.current) return;
    const ok = await api.ping();
    if (cancelled.current) return;

    if (ok) {
      attemptRef.current = 0;
      setAttempts(0);
      setStatus('online');
      schedule(POLL_WHEN_ONLINE);
      return;
    }

    attemptRef.current += 1;
    setAttempts(attemptRef.current);

    if (attemptRef.current >= RETRY_LIMIT) {
      setStatus('offline');
      return;
    }
    setStatus(attemptRef.current > WAKING_AFTER_ATTEMPTS ? 'waking' : 'connecting');
    // Ease off gradually, but keep probing often enough to catch the wake-up.
    schedule(Math.min(RETRY_BASE * Math.ceil(attemptRef.current / 4), 8000));
  };

  const retry = useCallback(() => {
    attemptRef.current = 0;
    setAttempts(0);
    setStatus('connecting');
    schedule(0);
  }, [schedule]);

  useEffect(() => {
    cancelled.current = false;
    probeRef.current();
    // A tab returning to the foreground should re-check immediately.
    const onVisible = () => {
      if (document.visibilityState === 'visible' && status !== 'online') retry();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled.current = true;
      clearTimeout(timerRef.current);
      document.removeEventListener('visibilitychange', onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { status, attempts, retry, isOnline: status === 'online' };
}
